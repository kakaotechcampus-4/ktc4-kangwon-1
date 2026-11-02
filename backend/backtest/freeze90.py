"""고정한 90점 후보를 로컬 원문으로 재현합니다. 실행 중 네트워크를 차단합니다.

backend에서 python -m backtest.freeze90 --output cache/frozen90-replay 를 실행합니다.
원문 DB·점포별 입력은 Git에 포함하지 않으며, 없으면 다운로드 없이 중단합니다.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL
from backtest.c4_blend import evaluate
from backtest.customer_trend_comparison import customer_panels
from backtest.offline import block_network, write_json
from backtest.support90 import MODES, score_saved

DEFAULT_MANIFEST = Path(__file__).with_name("data") / "frozen90-v1.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path, *, text=False):
    if not text:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    data = path.read_bytes()
    # Git의 Windows 줄바꿈 변환은 계산식 변경으로 취급하지 않습니다.
    if text:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def verify_files(root, entries, *, text=False):
    for relative, expected in entries.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("고정 입력 경로가 자료 폴더를 벗어납니다.")
        if not path.is_file():
            raise ValueError(f"로컬 고정 자료가 없습니다. 자동 다운로드하지 않습니다: {relative}")
        if digest(path, text=text) != expected:
            raise ValueError(f"고정한 파일과 해시가 다릅니다: {relative}")


def validate_cases(cases):
    ids = [case["id"] for case in cases]
    if len(cases) != 212 or len(set(ids)) != 212:
        raise ValueError("기존의 중복 없는 212곳을 모두 평가해야 합니다.")
    supported = set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL)
    if any(case["target"] not in INDUSTRIES for case in cases):
        raise ValueError("실제 업종이 고정한 51개 업종에 없습니다.")
    if sum(case["target"] in supported for case in cases) != 184:
        raise ValueError("지원 업종 보조 평가의 184곳을 유지해야 합니다.")
    return ids


def compact_metrics(value):
    return {
        key: value[key]
        for key in (
            "n",
            "hit5_n",
            "hit10_n",
            "mean_target_rank",
            "macro_hit5",
            "exposure5",
            "exposure10",
        )
    }


def run(data_root, out, manifest_path=DEFAULT_MANIFEST):
    if out.exists():
        raise ValueError("기존 재현 결과를 덮어쓰지 않습니다. 새 결과 경로를 지정하세요.")
    manifest = read(manifest_path)
    if manifest["nominal_total"] != 90 or manifest["modes"] != list(MODES):
        raise ValueError("고정한 90점의 세 가지 계산만 재현합니다.")
    backend = Path(__file__).resolve().parents[1]
    with block_network():
        verify_files(backend, manifest["implementation_sha256_lf"], text=True)
        verify_files(data_root, manifest["input_sha256"])
        paths = {name: data_root / value for name, value in manifest["inputs"].items()}
        cases = read(paths["cases"])["cases"]
        validate_cases(cases)
        calibration, background = read(paths["calibration"]), read(paths["background"])
        background["reference_quarter"] = "20252"
        raw, purchase = read(paths["lifecycle"]), read(paths["purchase"])
        reference, medical = read(paths["reference"]), read(paths["medical"])["sites"]
        city_day = read(paths["purchase_design"])["city_day_share"]
        areas, populations, _ = customer_panels(paths["database"], paths["population_dir"])
        orders, population_reference, cells = {}, {}, 0
        for index, case in enumerate(cases, 1):
            key = case["id"]
            saved = read(paths["saved_dir"] / f"{key}.json")
            expected = read(paths["expected_dir"] / f"{key}.json")
            area = saved["data"]["area_selection"]["area_code"]
            result = score_saved(
                saved,
                calibration,
                background,
                areas,
                populations,
                population_reference,
                raw["areas"][area],
                raw["city"],
                raw["quarters"],
                medical,
                purchase,
                reference,
                city_day,
            )
            orders[key] = result["orders"]
            for mode in MODES:
                method = "medical_only:" + mode
                if set(result["values"][mode]) != set(INDUSTRIES):
                    raise ValueError("원래 51개 후보를 모두 계산해야 합니다.")
                for code, value in result["values"][mode].items():
                    if not math.isclose(
                        value, expected["values"][method][code], rel_tol=0, abs_tol=1e-10
                    ):
                        raise ValueError(f"기존 점수가 재현되지 않습니다: {key}/{mode}/{code}")
                    cells += 1
                if orders[key][mode] != expected["orders"][method]:
                    raise ValueError(f"기존 순위가 재현되지 않습니다: {key}/{mode}")
            if orders[key]["popular"] != expected["orders"]["popular"]:
                raise ValueError(f"점포 수 기준선이 재현되지 않습니다: {key}")
            if index % 25 == 0:
                print(json.dumps({"sites_replayed": index, "score_cells": cells}), flush=True)
        scopes = {
            "all_212_candidates51": set(INDUSTRIES),
            "supported_184_candidates45": set(INDUSTRIES) - set(INDUSTRIES_WITHOUT_SEOUL),
        }
        metrics = {
            scope: {
                mode: compact_metrics(evaluate(cases, orders, mode, universe))
                for mode in (*MODES, "popular")
            }
            for scope, universe in scopes.items()
        }
        if metrics != manifest["development_metrics"]:
            raise ValueError("고정한 적중률·추천 노출 지표가 재현되지 않습니다.")
        report = {
            "passed": True,
            "n": len(cases),
            "score_cells": cells,
            "nominal_total": 90,
            "C4_full10_preserved": True,
            "development_metrics": metrics,
            "new_independent_validation": False,
            "operating_applied": False,
            "LLM_calls": 0,
            "map_calls": 0,
            "network_blocked": True,
            "manifest_sha256": digest(manifest_path),
        }
        out.mkdir(parents=True)
        write_json(out / "results.json", report)
        write_json(out / "orders.json", orders)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("cache/ab-evaluation"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true", help="자료·구현 해시만 검사")
    args = parser.parse_args()
    try:
        if args.verify_only:
            with block_network():
                manifest = read(DEFAULT_MANIFEST)
                verify_files(
                    Path(__file__).resolve().parents[1],
                    manifest["implementation_sha256_lf"],
                    text=True,
                )
                verify_files(args.data_root, manifest["input_sha256"])
            print(json.dumps({"verified": True, "LLM_calls": 0, "network_blocked": True}))
        else:
            report = run(args.data_root, args.output)
            print(json.dumps({k: v for k, v in report.items() if k != "development_metrics"}))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
