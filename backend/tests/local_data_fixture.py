"""부분 원천 대역을 실제 활성화 규칙에 맞는 완전한 자료 묶음으로 확장합니다."""

import hashlib
import json

from app.local_data.database import LocalDataDB
from app.seoul import previous_quarter


def complete_versions(db: LocalDataDB, versions: list[str], latest: str) -> list[str]:
    result = list(versions)
    metadata = [db.version(version) for version in versions]
    for source, count in (
        ("stores", 1),
        ("lifecycle", 12),
        ("floating", 5),
        ("resident", 1),
        ("worker", 1),
        ("areas", 1),
    ):
        existing = [version for version in metadata if version["source"] == source]
        seed = max(existing, key=lambda version: version["quarter"]) if existing else None
        rows = []
        if seed:
            with db.connection() as con:
                for raw in con.execute(
                    f"SELECT * FROM {source} WHERE version_id=?", (seed["version_id"],)
                ):
                    row = dict(raw)
                    row.pop("version_id")
                    row["payload"] = db.raw_row(source, seed["version_id"], row["row_key"])
                    rows.append(row)
        else:
            rows = [{"row_key": "fixture", "payload": {"value": 1}}]
        quarter = "" if source == "areas" else latest
        existing_quarters = {version["quarter"] for version in existing}
        for _ in range(count):
            if quarter not in existing_quarters:
                cloned = [{**row, "payload": dict(row["payload"])} for row in rows]
                for row in cloned:
                    if "STDR_YYQU_CD" in row["payload"]:
                        row["payload"]["STDR_YYQU_CD"] = quarter
                digest = hashlib.sha256(json.dumps(cloned, sort_keys=True).encode()).hexdigest()
                result.append(db.stage(source, quarter, cloned, digest))
            if source in ("lifecycle", "floating"):
                quarter = previous_quarter(quarter)
    return result
