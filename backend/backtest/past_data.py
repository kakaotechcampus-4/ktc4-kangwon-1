"""원본 DB를 보존하고 2025년 2분기까지만 담은 검증 전용 자료 묶음을 만듭니다."""

import csv
import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from app.agents.business_lifecycle.client import get_recent_quarters
from app.agents.commercial_area.client import CSV_FIELDS
from app.db.connection import readonly
from app.local_data.database import LocalDataDB
from app.local_data.refresh import normalize, store_rows
from backtest.licensing import sha256
from backtest.offline import block_network, write_json
from backtest.temporal_data import inventory, one_version

CUTOFF = "20252"
ARCHIVE_COLUMNS = {
    "기준_년분기_코드": "STDR_YYQU_CD",
    "상권_구분_코드": "TRDAR_SE_CD",
    "상권_구분_코드_명": "TRDAR_SE_CD_NM",
    "상권_코드": "TRDAR_CD",
    "상권_코드_명": "TRDAR_CD_NM",
    "서비스_업종_코드": "SVC_INDUTY_CD",
    "서비스_업종_코드_명": "SVC_INDUTY_CD_NM",
    "점포_수": "STOR_CO",
    "유사_업종_점포_수": "SIMILR_INDUTY_STOR_CO",
    "개업_율": "OPBIZ_RT",
    "개업_점포_수": "OPBIZ_STOR_CO",
    "폐업_률": "CLSBIZ_RT",
    "폐업_점포_수": "CLSBIZ_STOR_CO",
    "프랜차이즈_점포_수": "FRC_STOR_CO",
}


def checked_receipt(path: Path, receipt: Path) -> dict:
    meta = json.loads(receipt.read_text(encoding="utf-8"))
    if (
        meta.get("accepted") is False
        or sha256(path) != meta["sha256"]
        or path.stat().st_size != meta["bytes"]
    ):
        raise ValueError("공식 원문 파일의 검증 기록이 다릅니다.")
    return meta


def public_rows(source: Path, name: str, quarter: str) -> list[dict]:
    stem = "resident-20252-v2" if name == "resident" and quarter == CUTOFF else f"{name}-{quarter}"
    path = source / f"{stem}.json"
    meta = checked_receipt(path, source / f"{stem}-receipt.json")
    body = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = [{k.upper(): v for k, v in row.items()} for row in body.get("DATA", [])]
    if not rows or len(rows) != meta["row_n"]:
        raise ValueError("공식 원문 행 수가 없거나 다운로드 기록과 다릅니다.")
    seen = set()
    for row in rows:
        if str(row.get("STDR_YYQU_CD")) != quarter or quarter > CUTOFF:
            raise ValueError("고정 분기와 다른 미래·혼합 자료입니다.")
        key = (str(row.get("TRDAR_CD", row.get("MEGA_CD"))), row.get("SVC_INDUTY_CD"))
        if key in seen:
            raise ValueError("공식 원문 자연키가 중복됩니다.")
        seen.add(key)
    return rows


def archive_rows(source: Path, year: int, quarters: set[str]):
    path = source / f"lifecycle-archive-{year}.zip"
    checked_receipt(path, source / f"lifecycle-archive-{year}-receipt.json")
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.infolist() if m.filename.endswith(".csv")]
        if len(members) != 1:
            raise ValueError("연도별 개폐업 CSV를 하나로 확정할 수 없습니다.")
        raw = z.read(members[0])
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp949")
        reader = csv.DictReader(io.StringIO(text))
        if set(reader.fieldnames or []) != set(ARCHIVE_COLUMNS):
            raise ValueError("보관 CSV의 서울 API 대응 열이 다릅니다.")
        for original in reader:
            row = {target: original[key] for key, target in ARCHIVE_COLUMNS.items()}
            quarter = str(row["STDR_YYQU_CD"])
            if quarter in quarters:
                if quarter > CUTOFF:
                    raise ValueError("미래 보관 분기는 입력에 넣을 수 없습니다.")
                yield row


def check_overlap(data: Path, source: Path, versions: list[dict]) -> dict:
    fields = ("STOR_CO", "SIMILR_INDUTY_STOR_CO", "OPBIZ_STOR_CO", "CLSBIZ_STOR_CO", "FRC_STOR_CO")
    old = {}
    for row in archive_rows(source, 2023, {"20233", "20234"}):
        key = (row["STDR_YYQU_CD"], row["TRDAR_CD"], row["SVC_INDUTY_CD"])
        if key in old:
            raise ValueError("보관 개폐업 자연키 중복")
        old[key] = tuple(float(row[k]) for k in fields)
    seen, checks = set(), 0
    with readonly(data) as db:
        for q in ("20233", "20234"):
            version = one_version(versions, "lifecycle", q)
            columns = json.loads(version["columns_json"])
            indexes = [columns.index(k) for k in fields]
            for area, industry, payload in db.execute(
                "SELECT area_code,industry_code,payload FROM lifecycle WHERE version_id=?",
                (version["version_id"],),
            ):
                key = (q, area, industry)
                values = json.loads(payload)
                if key not in old or old[key] != tuple(float(values[i]) for i in indexes):
                    raise ValueError("보관 CSV와 현재 보관 DB의 중복 분기 건수가 다릅니다.")
                seen.add(key)
                checks += len(fields)
    if seen != set(old):
        raise ValueError("중복 분기의 원문 행 집합이 다릅니다.")
    return {"quarters": ["20233", "20234"], "matched_rows": len(seen), "count_checks": checks}


def copy_past(data: Path, target: LocalDataDB, versions: list[dict]) -> list[str]:
    selected = [
        v
        for v in versions
        if v["source"] in ("areas", "seoul_boundary")
        or (v["source"] == "lifecycle" and v["quarter"] <= CUTOFF)
        or (v["source"] == "floating" and v["quarter"] == CUTOFF)
    ]
    ids = [v["version_id"] for v in selected]
    with closing(sqlite3.connect(target.path.resolve().as_uri(), uri=True)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("ATTACH DATABASE ? AS original", (data.resolve().as_uri() + "?mode=ro",))
        placeholders = ",".join("?" for _ in ids)
        db.execute(
            "INSERT INTO data_versions SELECT * FROM original.data_versions "
            f"WHERE version_id IN ({placeholders})",
            ids,
        )
        db.execute(
            "INSERT INTO source_fields SELECT * FROM original.source_fields "
            f"WHERE version_id IN ({placeholders})",
            ids,
        )
        for source in ("areas", "seoul_boundary", "lifecycle", "floating"):
            db.execute(
                f"INSERT INTO {source} SELECT * FROM original.{source} "
                f"WHERE version_id IN ({placeholders})",
                ids,
            )
    return ids


def extract_stores(archive: Path, receipt: Path) -> tuple[Path, dict]:
    meta = checked_receipt(archive, receipt)
    folder = Path(tempfile.gettempdir()) / "chaeum-past80-source-20261027"
    folder.mkdir(exist_ok=True)
    path = folder / f"seoul-202506-{meta['sha256'][:12]}.csv"
    with zipfile.ZipFile(archive) as z:
        members = [m for m in z.infolist() if m.filename.endswith("_서울_202506.csv")]
        if len(members) != 1:
            raise ValueError("과거 서울 점포 CSV가 하나가 아닙니다.")
        member = members[0]
        if not path.exists():
            with z.open(member) as src, path.open("xb") as dest:
                shutil.copyfileobj(src, dest)
        if path.stat().st_size != member.file_size:
            raise ValueError("검증 전용 임시 점포 원문의 크기가 다릅니다.")
    return path, {
        "archive_sha256": meta["sha256"],
        "member": member.filename,
        "csv_sha256": sha256(path),
    }


def prepare(data: Path, source: Path, stores_source: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("과거 자료 묶음 폴더가 이미 있습니다.")
    with block_network():
        original_hash = sha256(data)
        versions = inventory(data)
        overlap = check_overlap(data, source, versions)
        out.mkdir(parents=True)
        target = LocalDataDB(out / "past.sqlite3")
        ids = copy_past(data, target, versions)
        for q in ("20223", "20224", "20231", "20232"):
            path = source / f"lifecycle-archive-{q[:4]}.zip"
            ids.append(
                target.stage(
                    "lifecycle",
                    q,
                    (
                        normalize("lifecycle", row, q)
                        for row in archive_rows(source, int(q[:4]), {q})
                    ),
                    sha256(path),
                )
            )
            print(json.dumps({"stage": "lifecycle_staged", "quarter": q}), flush=True)
        for q in ("20242", "20243", "20244", "20251"):
            path = source / f"floating-{q}.json"
            ids.append(
                target.stage(
                    "floating",
                    q,
                    (normalize("floating", row, q) for row in public_rows(source, "floating", q)),
                    sha256(path),
                )
            )
        for name in ("resident", "worker"):
            path = source / (
                "resident-20252-v2.json" if name == "resident" else "worker-20252.json"
            )
            ids.append(
                target.stage(
                    name,
                    CUTOFF,
                    (normalize(name, row, CUTOFF) for row in public_rows(source, name, CUTOFF)),
                    sha256(path),
                )
            )
        csv_path, stores_meta = extract_stores(
            stores_source / "stores-20250630.zip", stores_source / "stores-20250630-download.json"
        )
        print(json.dumps({"stage": "historical_stores_staging"}), flush=True)
        store_id = target.stage(
            "stores", CUTOFF, store_rows(csv_path, CSV_FIELDS), stores_meta["csv_sha256"]
        )
        target.validate_seoul_stores(store_id)
        ids.append(store_id)
        target.activate(ids)
        final_versions = inventory(target.path)
        for source_name, count in (("lifecycle", 12), ("floating", 5)):
            qs = sorted(v["quarter"] for v in final_versions if v["source"] == source_name)
            if qs != get_recent_quarters(CUTOFF, count):
                raise ValueError("검증 묶음에 과거 연속 분기가 부족합니다.")
        if any(v["quarter"] > CUTOFF for v in final_versions) or sha256(data) != original_hash:
            raise ValueError("미래 수치가 들어왔거나 원본 DB가 달라졌습니다.")
        manifest = {
            "cutoff": CUTOFF,
            "lifecycle_quarters": get_recent_quarters(CUTOFF, 12),
            "overlap_check": overlap,
            "store_source": stores_meta,
            "versions": final_versions,
            "original_db_sha256": original_hash,
            "original_db_unchanged": True,
            "code_sha256": sha256(Path(__file__)),
            "future_numeric_rows_used": 0,
            "limits": [
                "현재 보관본의 과거 분기 사용. 당시 공개 버전·현재 경계의 과거 동일성은 미확인"
            ],
        }
        write_json(out / "manifest.json", manifest)
    return manifest
