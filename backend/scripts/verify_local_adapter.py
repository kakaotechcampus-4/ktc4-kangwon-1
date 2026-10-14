"""저장 표본과 로컬 DB를 오프라인 비교합니다. 결과/요청 DB는 cache에만 둡니다."""

import asyncio
import json
import sys
import uuid
from collections import Counter
from functools import partial
from pathlib import Path
from time import monotonic
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.concurrency import run_in_thread  # noqa: E402
from app.config import load_environment  # noqa: E402
from app.db import repository  # noqa: E402
from app.db.connection import connect, initialize  # noqa: E402
from app.local_data.adapter import LocalAdapter  # noqa: E402
from app.local_data.persistence import persist_local  # noqa: E402
from app.schemas import AnalysisTask, Site  # noqa: E402
from app.storage.raw import capture_scope  # noqa: E402
from scripts.verify_rubric_reproduction import verify  # noqa: E402


def checkpoint(path):
    with connect(path) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


async def main():
    load_environment()
    folder = Path("cache/rubric_samples")
    golden = await run_in_thread(verify, folder)
    expected = json.loads(
        await run_in_thread(partial((folder / "dryrun-results.json").read_text, encoding="utf-8"))
    )["reports"]
    expected = {r["address"]: r for r in expected}
    path = await run_in_thread(initialize, Path("cache/ld3-performance-final.sqlite3"))
    perf, differences, badges = [], [], Counter()
    files = await run_in_thread(lambda: sorted(folder.glob("sample-*.json")))
    logic_path = await run_in_thread(initialize, Path("cache/ld3-logic.sqlite3"))
    matched = 0
    for number, file in enumerate(files, 1):
        sample = json.loads(await run_in_thread(partial(file.read_text, encoding="utf-8")))
        request = "ld3-" + str(number) + "-" + str(uuid.uuid4())
        task = AnalysisTask(
            request_id=request, site=Site.model_validate(sample["site"]), radius_m=500
        )
        before = (await run_in_thread(path.stat)).st_size
        started = monotonic()
        await run_in_thread(
            lambda request=request, sample=sample: repository.create_request(
                request, sample["address"], db_path=path
            )
        )
        with patch("httpx.AsyncClient", side_effect=AssertionError("기본자료 HTTP 금지")):
            async with capture_scope(request, path) as scope:
                adapter = await run_in_thread(LocalAdapter)
                data = await run_in_thread(adapter.analyze, task)
                # 지도·규제는 같은 저장 관측 대역을 써 기본자료 차이만 비교합니다.
                data["education_zones"] = sample["education_zones"]
                data["facilities"] = sample["facilities"]
                _, report, _ = await run_in_thread(persist_local, task, scope, adapter, data)
                await scope.finish()
        elapsed = monotonic() - started
        await run_in_thread(checkpoint, path)
        perf.append(
            {
                "address": sample["address"],
                "seconds": round(elapsed, 3),
                "db_increase": (await run_in_thread(path.stat)).st_size - before,
            }
        )
        old = {r["code"]: r for r in expected[sample["address"]]["rows"]}
        logic_request = "logic-" + str(uuid.uuid4())
        await run_in_thread(
            lambda request=logic_request, sample=sample: repository.create_request(
                request, sample["address"], db_path=logic_path
            )
        )
        async with capture_scope(logic_request, logic_path) as logic_scope:
            _, prepared, _ = await run_in_thread(persist_local, task, logic_scope, adapter, sample)
            await logic_scope.finish()
        for row in prepared["rows"]:
            keys = ("items", "lower", "upper", "applicable_weight", "badge", "coverage")
            if all(row[k] == old[row["code"]][k] for k in keys):
                matched += 1
            else:
                raise AssertionError("동일 입력의 로컬 전달/저장/채점 경로 불일치")
        for row in report["rows"]:
            badges[row["badge"]] += 1
            changed = [i for i in row["items"] if row["items"][i] != old[row["code"]]["items"][i]]
            if changed:
                differences.append(
                    {
                        "address": sample["address"],
                        "code": row["code"],
                        "old_badge": old[row["code"]]["badge"],
                        "new_badge": row["badge"],
                        "old_lower": old[row["code"]]["lower"],
                        "new_lower": row["lower"],
                        "items": changed,
                        "old_values": {i: old[row["code"]]["items"][i]["value"] for i in changed},
                        "new_values": {i: row["items"][i]["value"] for i in changed},
                    }
                )
        print(json.dumps(perf[-1], ensure_ascii=False), flush=True)
    result = {
        "golden": golden | {"local_prepared_matched": matched},
        "performance": perf,
        "differences": differences,
        "badges": dict(badges),
    }
    await run_in_thread(
        partial(
            Path("cache/ld3-results.json").write_text,
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    )

    print(
        json.dumps(
            {"golden": golden, "badges": dict(badges), "changed_rows": len(differences)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
