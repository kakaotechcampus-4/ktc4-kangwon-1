"""요청 범위 원문 수집·보안 정제·SQLite 저장입니다. 모델 호출은 없습니다."""

import json
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock

from app.canonical import canonical_hash, canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect, readonly
from app.storage.scrub import _AUTH_KEYS as _AUTH_KEYS
from app.storage.scrub import _auth as _auth
from app.storage.scrub import scrub as scrub

# 기존 검사와 이전 단계 호출의 임시 호환 이름입니다.
_json = canonical_json
_hash = canonical_hash
_now = utc_now_iso
_write = run_in_thread


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


def current_capture():
    return _SCOPE.get()


def _rows(payload):
    if not isinstance(payload, dict):
        return [], None
    if isinstance(payload.get("rows"), list):
        return payload["rows"], len(payload["rows"])
    if isinstance(payload.get("documents"), list):
        return payload["documents"], len(payload["documents"])
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
            ("s_" + str(uuid.uuid4()), request_id, run_id, utc_now_iso()),
        )
        return db.execute(
            "SELECT snapshot_id FROM snapshots WHERE request_id=?", (request_id,)
        ).fetchone()[0]


def _save_response(
    scope, *, source, source_type, args, page, status, payload, secrets=(), connection=None
):
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
        k: v
        for k, v in args.items()
        if k
        not in {
            "url",
            "start",
            "end",
            "page",
            "headers",
            "cache_hit",
            "original_collected_at",
            "cache_key",
        }
    }
    query = grouping.get("query")
    if isinstance(query, dict):
        grouping["query"] = {k: v for k, v in query.items() if k not in {"pageNo", "numOfRows"}}
    group_key = canonical_hash(grouping)
    response_id = "r_" + str(uuid.uuid4())
    payload_hash = canonical_hash(payload)
    with connect(scope.path) if connection is None else nullcontext(connection) as db:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        inserted = db.execute(
            "INSERT OR IGNORE INTO raw_payloads VALUES(?,?)",
            (payload_hash, canonical_json(payload)),
        ).rowcount
        if inserted:
            db.executemany(
                "INSERT OR IGNORE INTO raw_rows VALUES(?,?,?,?,?,?)",
                [
                    (
                        "rr_" + str(uuid.uuid4()),
                        payload_hash,
                        index,
                        _natural(row),
                        canonical_json(row),
                        canonical_hash(row),
                    )
                    for index, row in enumerate(rows)
                    if isinstance(row, dict)
                ],
            )
        duplicate = db.execute(
            "SELECT response_id FROM raw_responses WHERE snapshot_id=? AND run_id=? AND "
            "source=? AND group_key=? AND page=? ORDER BY collected_at LIMIT 1",
            (scope.snapshot_id, scope.run_id, source, group_key, str(page)),
        ).fetchone()
        db.execute(
            "INSERT INTO raw_responses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                response_id,
                scope.request_id,
                scope.run_id,
                scope.snapshot_id,
                source,
                source_type,
                canonical_json(args),
                str(page),
                status,
                utc_now_iso(),
                payload_hash,
                group_key,
                expected,
                duplicate[0] if duplicate else None,
            ),
        )
        for row_id, row_hash in db.execute(
            "SELECT raw_row_id,row_hash FROM raw_rows WHERE payload_hash=? ORDER BY row_index",
            (payload_hash,),
        ).fetchall():
            previous = db.execute(
                # 요청 전체 행 대신 같은 해시의 행부터 찾아 대용량 페이지의 반복 탐색을 막습니다.
                "SELECT r.raw_row_id FROM raw_rows r INDEXED BY raw_row_hash "
                "CROSS JOIN raw_response_rows e ON e.raw_row_id=r.raw_row_id "
                "CROSS JOIN raw_responses p ON p.response_id=e.response_id "
                "WHERE p.snapshot_id=? AND p.run_id=? "
                "AND p.source=? AND p.group_key=? AND r.row_hash=? LIMIT 1",
                (scope.snapshot_id, scope.run_id, source, group_key, row_hash),
            ).fetchone()
            db.execute(
                "INSERT INTO raw_response_rows VALUES(?,?,?)",
                (response_id, row_id, previous[0] if previous else None),
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
            (canonical_json(manifest), canonical_json(periods), scope.snapshot_id),
        )
    return response_id


def _finish(scope):
    with connect(scope.path) as db:
        groups = db.execute(
            "SELECT p.source,p.group_key,max(p.expected_rows),count(CASE WHEN "
            "e.duplicate_of IS NULL THEN e.raw_row_id END) FROM raw_responses p LEFT JOIN "
            "raw_response_rows e USING(response_id) WHERE p.snapshot_id=? AND p.run_id=? AND "
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
        previous = manifest.setdefault("runs", {}).get(scope.run_id, {})
        manifest["runs"][scope.run_id] = {
            "partial": previous.get("partial", False) or scope.partial or bool(gaps),
            "missing_pages": gaps,
            "reasons": sorted(scope.reasons | set(previous.get("reasons", []))),
        }
        partial = row[1] == "partial" or scope.partial or bool(gaps)
        # 원문 없는 목업 실행을 완전 수집으로 표시하지 않습니다.
        if not groups and not any(key != "runs" for key in manifest):
            partial = True
        db.execute(
            "UPDATE snapshots SET completeness=?,base_source_manifest=? WHERE snapshot_id=?",
            ("partial" if partial else "complete", canonical_json(manifest), scope.snapshot_id),
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
    # ponytail: 프로세스 내 요청 잠금입니다. 서버 여러 대면 작성자 조정을 재검토합니다.
    write_lock: object = field(default_factory=Lock, repr=False)
    cancelled: Event = field(default_factory=Event, repr=False)

    def incomplete(self, reason):
        self.partial = True
        self.finished = False
        self.reasons.add(reason)

    def record_sync(self, **kwargs):
        try:
            with self.write_lock:
                response_id = _save_response(self, **kwargs)
                self.finished = False
            return response_id
        except Exception as exc:
            raise RawStorageError("원문 저장에 실패했습니다.") from exc

    async def record(self, **kwargs):
        return await run_in_thread(lambda: self.record_sync(**kwargs))

    async def finish(self):
        def finish_locked():
            with self.write_lock:
                _finish(self)

        try:
            await run_in_thread(finish_locked)
            self.finished = True
        except Exception as exc:
            raise RawStorageError("원문 스냅샷 마무리에 실패했습니다.") from exc


@asynccontextmanager
async def capture_scope(request_id: str, path: Path):
    run_id = "run_" + str(uuid.uuid4())
    try:
        snapshot = await run_in_thread(_snapshot, request_id, run_id, path)
    except Exception as exc:
        raise RawStorageError("원문 스냅샷 생성에 실패했습니다.") from exc
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
        except Exception as exc:
            raise RawStorageError("원문 스냅샷 마무리에 실패했습니다.") from exc
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
        canonical_json(payload)
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
    with readonly(path) as db:
        db.create_function("raw_request_id", 0, lambda: request_id)
        db.create_function("raw_snapshot_id", 0, lambda: snapshot_id)
        yield db
