import argparse
import asyncio
import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

from app.agents.commercial_area.trade_areas import load_trade_areas
from app.config import load_environment
from app.industries.catalog import INDUSTRIES

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SECTIONS = {"quarter", "lifecycle", "floating", "density"}


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"backtest_script_{name}", SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"스크립트를 불러오지 못했습니다: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def density_percentiles(rows: list[dict], expected: set[str]) -> dict[str, dict[int, float]]:
    script = load_script("build_density_baseline")
    done = {row["code"]: row for row in rows if row["code"] in expected}
    if set(done) != expected:
        raise ValueError(f"상권 표본이 부족합니다: {len(done)}/{len(expected)}")
    result: dict[str, dict[int, float]] = {}
    for code in INDUSTRIES:
        values = [
            json.loads(row["counts"])[code] / script.area_km2(500)
            for row in done.values()
            if code not in json.loads(row["blocked_codes"])
        ]
        if len(values) != len(expected):
            raise ValueError(f"{code} 밀도 표본이 불완전합니다: {len(values)}/{len(expected)}")
        result[code] = dict(zip(script.STEPS, script.percentile_table(values), strict=True))
    return result


async def measure_all(quarter: str, seoul_csv: Path) -> dict[str, Any]:
    lifecycle_script = load_script("measure_lifecycle_baseline")
    with tempfile.TemporaryDirectory() as folder:
        audit = Path(folder) / "lifecycle.json"
        with patch.object(lifecycle_script, "AUDIT_PATH", audit):
            await lifecycle_script.run(quarter, 12)
        lifecycle = json.loads(audit.read_text(encoding="utf-8"))["values"]
    flpop_script = load_script("measure_flpop_baseline")
    async with flpop_script.BaselineClient() as client:
        records = await client.fetch_quarter(quarter)
    floating = flpop_script.measure(records, quarter, flpop_script.read_patterns())
    density_script = load_script("build_density_baseline")
    areas = load_trade_areas()
    rows = await asyncio.to_thread(density_script.sample_csv, Path(seoul_csv), quarter, areas)
    density = density_percentiles(rows, {area.code for area in areas})
    return {"quarter": quarter, "lifecycle": lifecycle, "floating": floating, "density": density}


def save_baselines(path: Path, values: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(values, ensure_ascii=False, indent=1), encoding="utf-8")
    temp.replace(target)


def load_baselines(path: Path) -> dict[str, Any]:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(values, dict) or not SECTIONS <= set(values):
        raise ValueError("기준선 파일 형식이 아닙니다.")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="과거 분기 서울 기준선을 측정해 저장합니다.")
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--seoul-csv", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.save.exists():
        parser.error("기준선 파일이 이미 있습니다. 다른 경로를 쓰세요.")
    load_environment()
    values = asyncio.run(measure_all(args.quarter, args.seoul_csv))
    save_baselines(args.save, values)
    report = {
        "saved": str(args.save),
        "lifecycle": len(values["lifecycle"]),
        "floating": sorted(values["floating"]),
        "density": len(values["density"]),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
