"""저장 좌표와 읽기 전용 자료 DB로 전체 업종 점수를 남깁니다. 네트워크는 차단합니다."""

import argparse
import hashlib
import json
import re
import socket
from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from app.agentic import scoring
from app.industries import DATA_DIR
from app.local_data.adapter import LocalAdapter
from app.schemas import AnalysisTask, Site
from backtest.comparison import METHODS, compare_rankings


@contextmanager
def block_network():
    def denied(*args, **kwargs):
        raise RuntimeError("오프라인 검증에서 네트워크 요청을 차단했습니다.")

    with ExitStack() as stack:
        for name in ("connect", "connect_ex", "sendto"):
            stack.enter_context(patch.object(socket.socket, name, denied))
        stack.enter_context(patch.object(socket, "getaddrinfo", denied))
        yield


def load_sites(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["sites"]
    ids = set()
    if not cases:
        raise ValueError("저장 좌표가 하나 이상 필요합니다.")
    for case in cases:
        name = case["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
            raise ValueError("사례 ID는 영문·숫자·밑줄·하이픈으로 작성하세요.")
        if name in ids:
            raise ValueError("사례 ID가 중복됩니다.")
        ids.add(name)
        Site.model_validate(case["site"])
        if case.get("radius_m", 500) != 500:
            raise ValueError("현재 오프라인 비교는 500m 기준선으로만 실행합니다.")
    return cases


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(sites_path: Path, data_path: Path, out: Path) -> dict:
    cases = load_sites(sites_path)
    if out.exists():
        raise ValueError("결과 폴더가 이미 있습니다. 새 경로를 지정하세요.")
    with block_network():
        adapter = LocalAdapter(data_path)
        latest = {
            source: max(v["quarter"] for v in adapter.versions if v["source"] == source)
            for source in ("stores", "floating", "lifecycle", "resident", "worker")
        }
        if set(latest.values()) != {scoring.BASELINE_BASE_QUARTER}:
            raise ValueError("현재 채점 기준선과 자료 DB의 최신 분기가 다릅니다.")
        out.mkdir(parents=True)
        (out / "sites.json").write_bytes(sites_path.read_bytes())
        results = []
        for case in cases:
            task = AnalysisTask(
                request_id="offline-" + case["id"],
                site=Site.model_validate(case["site"]),
                radius_m=500,
            )
            data = adapter.analyze(task)
            data["education_zones"] = {"status": "not_queried", "zones": []}
            data["facilities"] = {"data": {"queries": {}, "places": {}}}
            data.setdefault("limitations", []).append(
                "오프라인 검증: 지도 시설·규제·공간 조건·L 판단을 새로 조회하지 않았습니다."
            )
            report = scoring.evaluate(data)
            if {row["code"] for row in report["rows"]} != set(scoring.INDUSTRIES):
                raise ValueError("전체 51업종 채점 결과가 필요합니다.")
            comparison = compare_rankings(report["rows"])
            saved = {
                "id": case["id"],
                "site": task.site.model_dump(mode="json"),
                "radius_m": 500,
                "data": data,
                "scores": report["rows"],
                "comparison": comparison,
            }
            write_json(out / f"{case['id']}.json", saved)
            results.append(
                {
                    "id": case["id"],
                    "top5": comparison["top5"],
                    "quality": {
                        "without_D1_D3_observations": sum(
                            not any(
                                row["items"][name]["status"] == "observed" for name in ("D1", "D3")
                            )
                            for row in report["rows"]
                        ),
                        "guarded_eligible_n": sum(
                            row["ranks"]["guarded"] is not None for row in comparison["rows"]
                        ),
                        "unknown_item_counts": dict(
                            Counter(
                                name for row in comparison["rows"] for name in row["unknown_items"]
                            )
                        ),
                    },
                }
            )
    backend = Path(__file__).resolve().parents[1]
    source_paths = [
        backend / "app/agentic/scoring.py",
        Path(__file__),
        Path(__file__).with_name("comparison.py"),
        DATA_DIR / "industry_profile.csv",
        DATA_DIR / "industry_space_requirements.csv",
        backend / "app/agents/business_lifecycle/baseline.py",
        backend / "app/agents/commercial_area/baseline.py",
        backend / "app/agents/floating_population/baseline.py",
        backend / "app/industries/catalog.py",
    ]
    source_paths.extend(sorted((backend / "app/agents/floating_population/data").glob("*.csv")))
    manifest = {
        "kind": "current-data-offline-diagnostic",
        "llm_calls": 0,
        "network": "소켓 연결·DNS·UDP 전송 차단",
        "baseline_quarter": scoring.BASELINE_BASE_QUARTER,
        "data_path": str(data_path.resolve()),
        "data_versions": adapter.versions,
        "sites_sha256": hashlib.sha256(sites_path.read_bytes()).hexdigest(),
        "source_hashes": {
            str(path.relative_to(backend)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "case_count": len(cases),
        "industry_score_count": len(cases) * 51,
        "unobserved": ["지도 시설", "규제", "공간 조건", "L"],
        "experimental_guard": {
            "code_applicable_min": 60,
            "coverage_min": 0.75,
            "domain_coverage_min": 0.5,
            "requires_D1_or_D3": True,
        },
        "results": results,
    }
    write_json(out / "manifest.json", manifest)
    lines = [
        "# 현재 자료 오프라인 채점 비교",
        "",
        f"자료 기준 분기: {scoring.BASELINE_BASE_QUARTER}. "
        "LLM 호출 0회. 네트워크 차단 상태에서 실행했다.",
        "주소를 새로 변환하지 않고 제공된 좌표를 사용했다. 자료 DB는 읽기 전용으로 열었다.",
        "지도 시설·규제·공간 정보는 미확인이다. "
        "과거 245곳 백테스트나 최종 서비스 성능을 재현한 결과가 아니다.",
        "적합 업종 정답이 없는 사례이므로 적중률·생존율 개선을 주장하지 않는다.",
        "",
        "service는 현재 합산 순서, applicable은 미적용 배점을 제외한 90점 환산 하한, "
        "guarded는 자료 조건을 더한 실험이다.",
        "unknown 배점은 분모에 남긴다. 가드 조건은 실험값이며 운영 추천 규칙을 바꾸지 않았다.",
        "service는 검토 후보의 순서이며 추천 배지나 운영 가능성을 확정하는 결과가 아니다.",
        "",
        "| 사례 | 방식 | 상위 후보 |",
        "| --- | --- | --- |",
    ]
    for result in results:
        for method in METHODS:
            names = [scoring.INDUSTRIES[code] for code in result["top5"][method]]
            candidates = ", ".join(names) or "조건 충족 후보 없음"
            lines.append(f"| {result['id']} | {method} | {candidates} |")
    lines += [
        "",
        "## 자료 충족도",
        "",
        "| 사례 | D1·D3 관측이 없는 업종 수 | 실험 조건 통과 업종 수 |",
        "| --- | ---: | ---: |",
    ]
    for result in results:
        quality = result["quality"]
        lines.append(
            f"| {result['id']} | {quality['without_D1_D3_observations']} | "
            f"{quality['guarded_eligible_n']} |"
        )
    lines += ["", "## 방식별 후보 등장 횟수", ""]
    for method in METHODS:
        counts = Counter(code for result in results for code in result["top5"][method])
        lines.append(
            f"- {method}: "
            + ", ".join(
                f"{scoring.INDUSTRIES[code]} {count}회" for code, count in counts.most_common()
            )
        )
    lines += ["", "사례별 JSON에 51업종 전체 점수와 항목별 상태·사유, 원천 입력을 저장했다."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LLM·외부 API 없이 저장 좌표의 코드 채점을 비교합니다."
    )
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = run(args.sites, args.data, args.out)
    print(json.dumps({"cases": manifest["case_count"], "llm_calls": 0, "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
