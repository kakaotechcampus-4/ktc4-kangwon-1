"""요청 범위 원문 수집·보안 정제·SQLite 저장입니다. 모델 호출은 없습니다."""

import asyncio
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

from app.db.connection import connect


class RawStorageError(sqlite3.DatabaseError):
    """원문 저장 실패는 에이전트 실패로 변환하지 않고 서비스까지 전파합니다."""


def raise_storage_error(error: BaseException) -> None:
    """병렬 전송의 예외 그룹 안에 있는 저장 실패도 숨기지 않습니다."""
    if isinstance(error, RawStorageError):
        raise error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            raise_storage_error(child)


_SCOPE: ContextVar["CaptureScope | None"] = ContextVar("raw_capture", default=None)
_AUTH_KEYS = {
    "apikey",
    "servicekey",
    "authorization",
    "proxyauthorization",
    "referer",
    "referrer",
    "xapikey",
    "accesskey",
    "accesstoken",
    "token",
    "password",
    "cookie",
    "setcookie",
}


def _auth(name: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", name.lower()) in _AUTH_KEYS


def scrub(value, secrets=()):
    """모든 원천에서 같은 규칙으로 인증 필드·URL·응답에 반사된 키를 제거합니다."""
    if isinstance(value, dict):
        return {str(k): scrub(v, secrets) for k, v in value.items() if not _auth(str(k))}
    if isinstance(value, (tuple, list)):
        return [scrub(v, secrets) for v in value]
    if not isinstance(value, str):
        return value
    text = value
    for secret in secrets:
        if secret:
            for encoded in {secret, quote(secret, safe=""), quote_plus(secret)}:
                text = text.replace(encoded, "[REDACTED]")
    if text.startswith(("https://", "http://")):
        url = urlsplit(text)
        parts = url.path.split("/")
        if url.hostname == "openapi.seoul.go.kr" and len(parts) > 2:
            parts[1] = "[REDACTED]"
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if not _auth(k)]
        text = urlunsplit(
            (url.scheme, url.netloc.rsplit("@", 1)[-1], "/".join(parts), urlencode(query), "")
        )
    return text


def _json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


async def _write(fn, *args):
    """스레드 쓰기가 끝난 뒤 취소를 전파해 늦은 저장·마무리 경합을 막습니다."""
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


def current_capture():
    return _SCOPE.get()


def _rows(payload):
    if not isinstance(payload, dict):
        return [], None
    if isinstance(payload.get("rows"), list):
        return payload["rows"], len(payload["rows"])
    response = payload.get("response", payload)
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, dict):
        rows = body.get("items", [])
        if isinstance(rows, dict):
            rows = rows.get("item", [])
        if isinstance(rows, dict):
            rows = [rows]
        return rows if isinstance(rows, list) else [], body.get("totalCount")
    for service in payload.values():
        if isinstance(service, dict) and isinstance(service.get("row"), list):
            return service["row"], service.get("list_total_count")
    return [], None


def _natural(row):
    return ":".join(
        str(row.get(k, "")) for k in ("bizesId", "STDR_YYQU_CD", "TRDAR_CD", "SVC_INDUTY_CD")
    )


def _snapshot(request_id, run_id, path):
    with connect(path) as db:
        db.execute(
            "INSERT OR IGNORE INTO "
            "snapshots(snapshot_id,request_id,run_id,completeness,created_at) "
            "VALUES(?,?,?,'collecting',?)",
            ("s_" + str(uuid.uuid4()), request_id, run_id, _now()),
        )
        return db.execute(
            "SELECT snapshot_id FROM snapshots WHERE request_id=?", (request_id,)
        ).fetchone()[0]


def _save_response(scope, *, source, source_type, args, page, status, payload, secrets=()):
    args, payload = scrub(args, secrets), scrub(payload, secrets)
    rows, expected = _rows(payload)
    try:
        expected = int(expected) if expected is not None else None
    except (TypeError, ValueError):
        expected = None
    # 최신 분기 탐색 1행 요청은 전체 수집으로 간주하지 않습니다.
    if args.get("probe"):
        expected = None
    grouping = {
        k: v for k, v in args.items() if k not in {"url", "start", "end", "page", "headers"}
    }
    query = grouping.get("query")
    if isinstance(query, dict):
        grouping["query"] = {k: v for k, v in query.items() if k not in {"pageNo", "numOfRows"}}
    group_key = _hash(grouping)
    response_id = "r_" + str(uuid.uuid4())
    with connect(scope.path) as db:
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute(
            "SELECT response_id FROM raw_responses WHERE snapshot_id=? AND run_id=? AND "
            "source=? AND group_key=? AND page=? ORDER BY collected_at LIMIT 1",
            (scope.snapshot_id, scope.run_id, source, group_key, str(page)),
        ).fetchone()
        db.execute(
            "INSERT INTO raw_responses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                response_id,
                scope.request_id,
                scope.run_id,
                scope.snapshot_id,
                source,
                source_type,
                _json(args),
                str(page),
                status,
                _json(payload),
                _now(),
                _hash(payload),
                group_key,
                expected,
                duplicate[0] if duplicate else None,
            ),
        )
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            natural = _natural(row)
            previous = db.execute(
                "SELECT r.raw_row_id FROM raw_rows r JOIN raw_responses p "
                "USING(response_id) WHERE p.snapshot_id=? AND p.run_id=? AND p.source=? "
                "AND p.group_key=? AND r.natural_key=? AND r.raw_json=? LIMIT 1",
                (scope.snapshot_id, scope.run_id, source, group_key, natural, _json(row)),
            ).fetchone()
            db.execute(
                "INSERT INTO raw_rows VALUES(?,?,?,?,?,?)",
                (
                    "rr_" + str(uuid.uuid4()),
                    response_id,
                    index,
                    natural,
                    _json(row),
                    previous[0] if previous else None,
                ),
            )
        snap = db.execute(
            "SELECT base_source_manifest,source_periods FROM snapshots WHERE snapshot_id=?",
            (scope.snapshot_id,),
        ).fetchone()
        manifest, periods = json.loads(snap[0]), json.loads(snap[1])
        manifest.setdefault(source, {"source_type": source_type})
        if source_type == "file":
            manifest[source].update(file_hash=args["file_hash"], file_name=args["file_name"])
        quarter = args.get("quarter") or args.get("extra", "").split("/")[0]
        if quarter:
            periods[source] = sorted(set(periods.get(source, [])) | {str(quarter)})
        db.execute(
            "UPDATE snapshots SET base_source_manifest=?,source_periods=? WHERE snapshot_id=?",
            (_json(manifest), _json(periods), scope.snapshot_id),
        )
    return response_id


def _finish(scope):
    with connect(scope.path) as db:
        groups = db.execute(
            "SELECT p.source,p.group_key,max(p.expected_rows),count(CASE WHEN "
            "r.duplicate_of IS NULL THEN r.raw_row_id END) FROM raw_responses p LEFT JOIN "
            "raw_rows r USING(response_id) WHERE p.snapshot_id=? AND p.run_id=? AND "
            "p.duplicate_of IS NULL GROUP BY p.source,p.group_key",
            (scope.snapshot_id, scope.run_id),
        ).fetchall()
        gaps = [
            {"source": r[0], "group_key": r[1], "expected": r[2], "captured": r[3]}
            for r in groups
            if r[2] is not None and r[3] < r[2]
        ]
        row = db.execute(
            "SELECT base_source_manifest,completeness FROM snapshots WHERE snapshot_id=?",
            (scope.snapshot_id,),
        ).fetchone()
        manifest = json.loads(row[0])
        manifest.setdefault("runs", {})[scope.run_id] = {
            "partial": scope.partial or bool(gaps),
            "missing_pages": gaps,
            "reasons": sorted(scope.reasons),
        }
        partial = row[1] == "partial" or scope.partial or bool(gaps)
        # 원문 없는 목업 실행을 완전 수집으로 표시하지 않습니다.
        if not groups and not any(key != "runs" for key in manifest):
            partial = True
        db.execute(
            "UPDATE snapshots SET completeness=?,base_source_manifest=? WHERE snapshot_id=?",
            ("partial" if partial else "complete", _json(manifest), scope.snapshot_id),
        )


@dataclass
class CaptureScope:
    request_id: str
    path: Path
    run_id: str
    snapshot_id: str
    partial: bool = False
    finished: bool = False
    reasons: set[str] = field(default_factory=set)

    def incomplete(self, reason):
        self.partial = True
        self.finished = False
        self.reasons.add(reason)

    def record_sync(self, **kwargs):
        try:
            response_id = _save_response(self, **kwargs)
            self.finished = False
            return response_id
        except Exception:
            raise RawStorageError("원문 저장에 실패했습니다.") from None

    async def record(self, **kwargs):
        return await _write(lambda: self.record_sync(**kwargs))

    async def finish(self):
        try:
            await _write(_finish, self)
            self.finished = True
        except Exception:
            raise RawStorageError("원문 스냅샷 마무리에 실패했습니다.") from None


@asynccontextmanager
async def capture_scope(request_id: str, path: Path):
    run_id = "run_" + str(uuid.uuid4())
    try:
        snapshot = await _write(_snapshot, request_id, run_id, path)
    except Exception:
        raise RawStorageError("원문 스냅샷 생성에 실패했습니다.") from None
    scope = CaptureScope(request_id, path, run_id, snapshot)
    token = _SCOPE.set(scope)
    try:
        yield scope
    except BaseException:
        if not scope.finished:
            scope.incomplete("collection_interrupted")
        raise
    finally:
        try:
            if not scope.finished:
                await scope.finish()
        except Exception:
            raise RawStorageError("원문 스냅샷 마무리에 실패했습니다.") from None
        finally:
            _SCOPE.reset(token)


async def capture_http(source, response, *, args=None, page="1", secrets=()):
    scope = current_capture()
    if scope is None:
        return
    request = response.request
    credentials = list(secrets)
    credentials.extend(v for k, v in request.url.params.multi_items() if _auth(k))
    credentials.extend(v for k, v in request.headers.items() if _auth(k))
    credentials.extend(
        v.partition(" ")[2]
        for k, v in request.headers.items()
        if k.lower() in {"authorization", "proxy-authorization"} and " " in v
    )
    try:
        payload = response.json()
        _json(payload)
    except (ValueError, TypeError):
        payload = {"unparsed_text": response.text}
        scope.incomplete(source + ":invalid_json")
    if response.status_code >= 400:
        scope.incomplete(source + ":http_error")
    await scope.record(
        source=source,
        source_type="api",
        args=args or {"url": str(request.url), "query": dict(request.url.params)},
        page=str(page),
        status=response.status_code,
        payload=payload,
        secrets=credentials,
    )


@contextmanager
def scoped_reader(path, request_id, snapshot_id):
    """뷰 조회 범위는 실행기가 지정합니다. 모델에게 이 연결 설정 권한을 주지 않습니다."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.create_function("raw_request_id", 0, lambda: request_id)
        db.create_function("raw_snapshot_id", 0, lambda: snapshot_id)
        yield db
    finally:
        db.close()
