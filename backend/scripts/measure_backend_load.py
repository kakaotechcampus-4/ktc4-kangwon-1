"""임시 SQLite와 ASGI·대역으로만 부하를 측정합니다. 배포 처리량 시험이 아닙니다."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import inspect
import json
import os
import socket
import sqlite3
import statistics
import sys
import threading
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import repository  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.mocking import mock_dependencies  # noqa: E402
from app.services.settings import ExecutionSettings  # noqa: E402


def rss_bytes() -> int:
    """현재 프로세스 RSS를 읽습니다. Windows에서는 working set을 사용합니다."""
    if os.name == "nt":

        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in ("peak", "rss", "pool_peak", "pool", "non_peak", "non", "page", "pp")
            ]

        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not info(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
        return counters.rss
    # Linux 측정은 현재 RSS를 사용하며 최고 RSS와 혼용하지 않습니다.
    pages = int(Path("/proc/self/statm").read_text().split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE")


def distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered) * 1000, 3) if ordered else 0,
        "p95_ms": round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)] * 1000, 3)
        if ordered
        else 0,
        "max_ms": round(max(ordered, default=0) * 1000, 3),
    }


async def measure(scenario: str, concurrency: int, db_path: Path) -> dict:
    if scenario not in {"execution", "events"} or concurrency not in {10, 50, 100}:
        raise ValueError("지원하는 시나리오와 동시 요청 수를 지정하세요.")

    # 운영 DB나 이전 측정 파일은 열지 않습니다. 새 파일을 독점 생성합니다.
    def prepare_file():
        resolved = db_path.resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("xb"):
            pass
        return resolved

    db_path = await asyncio.to_thread(prepare_file)
    counts: Counter = Counter()
    fake: Counter = Counter(dict.fromkeys(("model", "api", "api_ok", "external_failures"), 0))
    outcomes: Counter = Counter(dict.fromkeys(("completed", "rejected", "cancelled", "failed"), 0))
    latencies: list[float] = []
    completed_latencies: list[float] = []
    statuses: set[str] = set()
    lags: list[float] = []
    rss_samples: list[int] = []
    lock = threading.Lock()
    delay = threading.Event()
    original_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        def execute(self, *args, **kwargs):
            # DB 작업은 실제 코드가 to_thread로 넘긴 스레드에서 지연됩니다.
            if args and str(args[0]).startswith("BEGIN IMMEDIATE"):
                delay.wait(0.001)
            with lock:
                counts["statements"] += 1
            try:
                return super().execute(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    with lock:
                        counts["locks"] += 1
                raise

    def connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=Connection)

    def dependencies(*args, **kwargs):
        bundle = mock_dependencies(*args, **kwargs)

        def wrap(fn, kind):
            async def invoke(*inputs, **options):
                fake[kind] += 1
                await asyncio.sleep(0.03 if kind == "model" else 0.005)
                if kind == "api" and inputs[0].site.input_address.endswith("failure"):
                    fake["external_failures"] += 1
                    raise RuntimeError("대역 외부 실패")
                result = fn(*inputs, **options)
                return await result if inspect.isawaitable(result) else result

            return invoke

        bundle["generate"] = wrap(bundle["generate"], "model")
        for field in ("generate_specialists", "generate_evaluators"):
            bundle[field] = {key: wrap(fn, "model") for key, fn in bundle[field].items()}
        if "agents" in bundle:
            bundle["agents"] = {
                key: wrap(fn, "api") if key == "floating_population" else wrap(fn, "api_ok")
                for key, fn in bundle["agents"].items()
            }
        return bundle

    async def sample():
        while True:
            start = time.perf_counter()
            await asyncio.sleep(0.01)
            lags.append(max(0, time.perf_counter() - start - 0.01))
            rss_samples.append(rss_bytes())

    settings = ExecutionSettings(
        db_path=db_path, analysis_mode="multi_agent", evaluators_enabled=True, max_concurrency=2
    )
    with (
        patch("sqlite3.connect", side_effect=connect),
        patch("app.api.v1.routes.mock_dependencies", side_effect=dependencies),
        patch("openai.AsyncOpenAI", side_effect=AssertionError("실제 LLM 생성 금지")),
        patch.object(socket.socket, "connect", side_effect=AssertionError("외부 연결 금지")),
    ):
        app = create_app(settings=settings, load_env=False)
        async with app.router.lifespan_context(app):
            if scenario == "events":
                for state in ("running", "completed"):
                    await asyncio.to_thread(
                        repository.create_request, state, "fixture", db_path=db_path
                    )
                    await asyncio.to_thread(repository.mark_running, state, db_path=db_path)
                    await asyncio.to_thread(
                        repository.append_event, state, "run", "started", {}, db_path=db_path
                    )

                # 이벤트 읽기 시험에만 쓰이는 완료 상태 fixture입니다.
                def finish_fixture():
                    with closing(original_connect(db_path)) as db, db:
                        db.execute(
                            "UPDATE analysis_requests SET status='completed', "
                            "completed_at='2026-10-03T00:00:00Z', "
                            "result_json=json_object('request_id', 'completed') "
                            "WHERE request_id='completed'"
                        )

                await asyncio.to_thread(finish_fixture)
            # 초기화와 fixture 구성 비용은 측정 구간에 넣지 않습니다.
            counts.clear()
            timer = time.perf_counter()
            cpu = time.process_time()
            rss_samples.append(rss_bytes())
            sampler = asyncio.create_task(sample())
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://asgi"
            ) as client:

                async def send(index):
                    started = time.perf_counter()
                    try:
                        if scenario == "events":
                            state = "running" if index % 2 else "completed"
                            response = await client.get(f"/api/v1/analyses/{state}/events")
                            if response.status_code == 200:
                                statuses.add(response.json()["status"])
                        else:
                            response = await client.post(
                                "/api/v1/analyses?mock=true&wait=true",
                                json={"address": "fixture-failure" if index == 0 else "fixture"},
                            )
                        result = (
                            "rejected"
                            if response.status_code == 429
                            else ("completed" if response.status_code == 200 else "failed")
                        )
                        outcomes[result] += 1
                        if result == "completed":
                            completed_latencies.append(time.perf_counter() - started)
                    except asyncio.CancelledError:
                        outcomes["cancelled"] += 1
                    finally:
                        latencies.append(time.perf_counter() - started)

                tasks = [asyncio.create_task(send(index)) for index in range(concurrency)]
                if scenario == "execution":
                    await asyncio.sleep(0.02)
                    tasks[1].cancel()
                await asyncio.gather(*tasks)
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
            elapsed = time.perf_counter() - timer
            cpu_used = time.process_time() - cpu
    return {
        "fixture": "ASGI + fake API/model; model=30ms API=5ms BEGIN delay requested=1ms; slots=2",
        "scenario": scenario,
        "submitted": concurrency,
        "admitted": concurrency - outcomes["rejected"],
        "outcomes": dict(outcomes),
        "latency": distribution(latencies),
        "completed_latency": distribution(completed_latencies),
        "elapsed_seconds": round(elapsed, 4),
        "cpu_seconds": round(cpu_used, 4),
        "rss_peak_sampled_bytes": max(rss_samples),
        "loop_lag": distribution(lags),
        "db_statements": counts["statements"],
        "db_lock_errors": counts["locks"],
        "fake_calls": dict(fake),
        "external_calls": 0,
        "event_statuses": sorted(statuses),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("execution", "events"), required=True)
    parser.add_argument("--concurrency", type=int, choices=(10, 50, 100), required=True)
    parser.add_argument("--db-path", type=Path, required=True, help="아직 없는 임시 SQLite 파일")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(measure(args.scenario, args.concurrency, args.db_path)), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
