import argparse
import json
from pathlib import Path
from typing import Any

from app.schemas import AgentAnalysis, Scope


class BusinessLifecycleFormatterError(RuntimeError):
    """Business Lifecycle 결과 변환 오류."""


def determine_status(
    scored_count: int,
    unscored_count: int,
) -> str:
    """
    분석 결과를 기반으로 Agent 상태를 결정한다.

    ok:
        모든 업종 분석 가능

    partial:
        일부 업종은 분석 가능하지만
        일부 업종은 데이터 부족

    no_data:
        분석 가능한 업종이 하나도 없음
    """

    if scored_count == 0:
        return "no_data"

    if unscored_count > 0:
        return "partial"

    return "ok"


def format_scored_industry(
    industry: dict[str, Any],
) -> dict[str, Any]:
    """
    LLM 분석이 완료된 업종을
    중재 Agent용 공통 형태로 변환한다.
    """

    return {
        "industry_id": industry[
            "industry_id"
        ],
        "industry_name": industry[
            "industry_name"
        ],

        "score": industry[
            "lifecycle_score"
        ],

        "type": industry[
            "type"
        ],

        "confidence": industry[
            "confidence"
        ],

        "data_available": True,
        "score_available": True,

        "evidence": industry.get(
            "evidence",
            [],
        ),

        "warning": industry.get(
            "warning"
        ),
    }


def format_unscored_industry(
    industry: dict[str, Any],
) -> dict[str, Any]:
    """
    데이터 부족 등의 이유로 Lifecycle Score를
    계산하지 못한 업종을 판단 보류 형태로 변환한다.
    """

    return {
        "industry_id": industry[
            "industry_id"
        ],
        "industry_name": industry[
            "industry_name"
        ],

        "score": None,

        "type": "판단 보류",

        "confidence": industry.get(
            "confidence",
            "none",
        ),

        "data_available": industry.get(
            "data_available",
            False,
        ),

        "score_available": False,

        "evidence": [],

        "warning": industry.get(
            "missing_reason",
            "분석에 필요한 데이터가 부족합니다.",
        ),
    }


def build_warnings(
    industries: list[dict[str, Any]],
) -> list[str]:
    """
    전체 분석 결과에 대한 해석상 주의사항을 생성한다.
    """

    warnings: list[str] = []

    unscored_count = sum(
        1
        for industry in industries
        if not industry["score_available"]
    )

    low_confidence_count = sum(
        1
        for industry in industries
        if (
            industry["score_available"]
            and industry["confidence"] == "low"
        )
    )

    if unscored_count > 0:
        warnings.append(
            f"70개 업종 중 {unscored_count}개 업종은 "
            "데이터 부족 또는 직접 대응 데이터 부재로 "
            "Lifecycle Score를 계산하지 못했습니다."
        )

    if low_confidence_count > 0:
        warnings.append(
            f"점수가 계산된 업종 중 "
            f"{low_confidence_count}개 업종은 "
            "표본 규모가 작아 confidence가 low입니다."
        )

    warnings.append(
        "Lifecycle Score는 미래 생존 확률이 아니라 "
        "분석 가능한 업종끼리 비교한 상대적 "
        "개폐업 안정성 점수입니다."
    )

    return warnings


def format_for_mediator(
    agent_result: dict[str, Any],
    *,
    scope_area: str | None = None,
    scope_period: str | None = None,
    metadata: dict[str, Any] | None = None,
    extra_warnings: list[str] | None = None,
) -> AgentAnalysis:
    """
    Business Lifecycle Agent의 내부 결과를
    중재 Agent 공통 형식으로 변환한다.

    반환 구조:

    {
        request_id,
        agent_id,
        status,
        scope,
        data,
        warnings
    }
    """

    request_id = agent_result.get(
        "request_id"
    )

    if not request_id:
        raise BusinessLifecycleFormatterError(
            "request_id가 없습니다."
        )

    agent_id = agent_result.get(
        "agent_id"
    )

    if agent_id != "business_lifecycle":
        raise BusinessLifecycleFormatterError(
            "agent_id가 business_lifecycle이 아닙니다."
        )

    scored_industries = agent_result.get(
        "industry_scores",
        [],
    )

    unscored_industries = agent_result.get(
        "unavailable_industries",
        [],
    )

    if not isinstance(
        scored_industries,
        list,
    ):
        raise BusinessLifecycleFormatterError(
            "industry_scores가 list가 아닙니다."
        )

    if not isinstance(
        unscored_industries,
        list,
    ):
        raise BusinessLifecycleFormatterError(
            "unavailable_industries가 list가 아닙니다."
        )

    # ========================================================
    # 1. 점수 있는 업종
    # ========================================================

    industries: list[
        dict[str, Any]
    ] = []

    for industry in scored_industries:
        industries.append(
            format_scored_industry(
                industry
            )
        )

    # ========================================================
    # 2. 판단 보류 업종
    # ========================================================

    for industry in unscored_industries:
        industries.append(
            format_unscored_industry(
                industry
            )
        )

    # ========================================================
    # 3. 업종 ID 기준 정렬
    # ========================================================

    industries.sort(
        key=lambda item: item[
            "industry_id"
        ]
    )

    # ========================================================
    # 4. 70개 Master 검증
    # ========================================================

    if len(industries) != 70:
        raise BusinessLifecycleFormatterError(
            "Business Lifecycle 결과의 업종 수가 "
            f"70개가 아닙니다. "
            f"현재={len(industries)}"
        )

    industry_ids = [
        industry["industry_id"]
        for industry in industries
    ]

    if len(set(industry_ids)) != 70:
        raise BusinessLifecycleFormatterError(
            "중복된 industry_id가 존재합니다."
        )

    expected_ids = set(
        range(1, 71)
    )

    actual_ids = set(
        industry_ids
    )

    if expected_ids != actual_ids:
        missing_ids = sorted(
            expected_ids - actual_ids
        )

        extra_ids = sorted(
            actual_ids - expected_ids
        )

        raise BusinessLifecycleFormatterError(
            "70개 Master industry_id가 일치하지 않습니다. "
            f"누락={missing_ids}, "
            f"추가={extra_ids}"
        )

    # ========================================================
    # 5. Coverage 계산
    # ========================================================

    scored_count = sum(
        1
        for industry in industries
        if industry["score_available"]
    )

    unscored_count = (
        len(industries)
        - scored_count
    )

    coverage = {
        "target_industries": 70,
        "scored_industries":
            scored_count,
        "unscored_industries":
            unscored_count,
    }

    # ========================================================
    # 6. Status
    # ========================================================

    status = determine_status(
        scored_count=scored_count,
        unscored_count=unscored_count,
    )

    scope = build_scope(
        agent_result=agent_result,
        scope_area=scope_area,
        scope_period=scope_period,
    )

    # ========================================================
    # 7. Warnings
    # ========================================================

    warnings = build_warnings(
        industries
    )

    if extra_warnings:
        warnings.extend(extra_warnings)

    warnings = list(
        dict.fromkeys(
            warning
            for warning in warnings
            if warning
        )
    )

    # ========================================================
    # 8. 중재 Agent 공통 반환 구조
    # ========================================================

    data: dict[str, Any] = {}

    if status != "no_data":
        data = {
            "summary": agent_result.get(
                "summary",
                "",
            ),

            "metadata": build_metadata(
                agent_result=agent_result,
                metadata=metadata,
            ),

            "coverage": coverage,

            "scoring_method":
                agent_result.get(
                    "scoring_method",
                    {},
                ),

            "industries":
                industries,
        }

    formatted_result: dict[
        str,
        Any,
    ] = {
        "request_id": request_id,

        "agent_id":
            "business_lifecycle",

        "status": status,

        "scope": scope.model_dump(),

        "data": data,

        "warnings": warnings,
    }

    return AgentAnalysis.model_validate(formatted_result)


def build_scope(
    *,
    agent_result: dict[str, Any],
    scope_area: str | None,
    scope_period: str | None,
) -> Scope:
    raw_scope = agent_result.get("scope", {})
    period = raw_scope.get("period", {})

    area = (
        scope_area
        or raw_scope.get("area")
        or raw_scope.get("area_name")
        or raw_scope.get("area_code")
        or "서울시 상권"
    )

    if scope_period:
        period_label = scope_period
    elif isinstance(period, dict):
        start = period.get("start_quarter")
        end = period.get("end_quarter")
        count = period.get("quarter_count")
        if start and end and count:
            period_label = f"{start}~{end} ({count}개 분기)"
        else:
            period_label = str(raw_scope.get("base_quarter") or "기준 기간 확인 불가")
    else:
        period_label = str(period or raw_scope.get("base_quarter") or "기준 기간 확인 불가")

    return Scope(
        area=str(area),
        period=period_label,
    )


def build_metadata(
    *,
    agent_result: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_scope = agent_result.get("scope", {})
    period = raw_scope.get("period", {})
    result_metadata = {
        "area_code": raw_scope.get("area_code"),
        "area_name": raw_scope.get("area_name"),
        "base_quarter": raw_scope.get("base_quarter"),
        "period": period if isinstance(period, dict) else None,
        "quarter_count": period.get("quarter_count") if isinstance(period, dict) else None,
    }
    if metadata:
        result_metadata.update(metadata)
    return {
        key: value
        for key, value in result_metadata.items()
        if value is not None
    }


def main() -> None:
    """
    formatter.py 단독 테스트용 CLI.

    실제 서비스에서는 JSON 파일을 읽지 않고
    agent.py가 format_for_mediator()를 직접 호출한다.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Business Lifecycle Agent 결과를 "
            "중재 Agent 공통 형식으로 변환"
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Business Lifecycle Agent "
            "결과 JSON 파일"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "중재 Agent용 JSON 저장 경로"
        ),
    )

    args = parser.parse_args()

    input_path = Path(
        args.input
    )

    output_path = Path(
        args.output
    )

    with input_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        agent_result = json.load(
            file
        )

    formatted_result = (
        format_for_mediator(
            agent_result
        )
    )

    formatted_payload = formatted_result.model_dump()

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            formatted_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "===== Formatter 완료 ====="
    )

    print(
        "request_id:",
        formatted_payload[
            "request_id"
        ],
    )

    print(
        "agent_id:",
        formatted_payload[
            "agent_id"
        ],
    )

    print(
        "status:",
        formatted_payload[
            "status"
        ],
    )

    coverage = formatted_payload[
        "data"
    ].get("coverage", {})

    print(
        "전체 업종:",
        coverage.get(
            "target_industries",
            0,
        ),
    )

    print(
        "점수 계산 업종:",
        coverage.get(
            "scored_industries",
            0,
        ),
    )

    print(
        "판단 보류 업종:",
        coverage.get(
            "unscored_industries",
            0,
        ),
    )

    print()
    print(
        "중재 Agent용 JSON 저장 완료:",
        output_path,
    )


if __name__ == "__main__":
    main()
