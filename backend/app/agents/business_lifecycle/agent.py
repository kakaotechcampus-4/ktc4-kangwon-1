import argparse
import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.schemas import AgentAnalysis, AgentError, AgentId, AnalysisTask, Scope, Site

from .area_resolver import (
    BusinessArea,
    BusinessAreaNoDataError,
    BusinessAreaResolverError,
    resolve_area,
)
from .client import (
    FutureQuarterError,
    SeoulOpenAPIError,
    SeoulOpenAPINoDataError,
    detect_latest_valid_quarter,
)
from .config import Settings, load_dotenv_if_present
from .formatter import BusinessLifecycleFormatterError, format_for_mediator
from .make_agent_input import build_agent_input

AGENT_ID: AgentId = "business_lifecycle"
DEFAULT_MODEL_NAME = "gpt-5.6-luna"

BATCH_SIZE = 10

ResolveArea = Callable[[Site, Settings], BusinessArea]
RunPipeline = Callable[[str, str, int, str | None, str | None], dict[str, Any]]


SYSTEM_PROMPT = """
당신은 상권의 업종별 개폐업 안정성을 분석하는
Business Lifecycle Agent입니다.

당신의 역할은 Python에서 이미 계산된 개폐업 데이터를
해석하여 업종별 상태를 설명하는 것입니다.

중요:
당신은 새로운 점수를 계산하지 않습니다.
입력으로 제공된 lifecycle_score와 각 지표를 그대로 사용합니다.

==================================================
[분석 데이터]
==================================================

입력 데이터는 기준 분기를 포함한 최근 12개 분기,
즉 약 3년의 개폐업 데이터를 기반으로 합니다.

각 업종에는 다음과 같은 지표가 제공될 수 있습니다.

1. observed_quarters
- 실제 데이터가 존재하는 분기 수

2. latest_store_count
- 가장 최근 기준분기의 점포 수

3. avg_store_count
- 전체 분석기간의 평균 점포 수

4. period_open_count
- 전체 분석기간 총 개업 수

5. period_close_count
- 전체 분석기간 총 폐업 수

6. period_net_change
- 전체 분석기간 개업 수 - 폐업 수

7. avg_close_rate
- 전체 분석기간 점포 규모를 고려한 폐업 수준

8. net_change_rate
- 전체 분석기간 순증감률
- 양수이면 개업이 폐업보다 많았음을 의미
- 음수이면 폐업이 개업보다 많았음을 의미

9. turnover_rate
- 개업과 폐업이 얼마나 활발하게 발생했는지를 나타내는 지표
- 높다고 반드시 좋은 것은 아니다
- 지나치게 높으면 업종 교체가 활발한 불안정한 상태일 수 있다

10. recent_year_close_rate
- 가장 최근 4개 분기의 폐업률

11. recent_year_net_change_rate
- 가장 최근 4개 분기의 순증감률

12. oldest_year_close_rate
- 분석기간 초반 4개 분기의 폐업률

13. close_rate_trend
- recent_year_close_rate - oldest_year_close_rate

close_rate_trend < 0:
과거보다 최근 폐업률이 낮아졌으므로 개선 방향

close_rate_trend > 0:
과거보다 최근 폐업률이 높아졌으므로 악화 방향

==================================================
[Lifecycle Score]
==================================================

lifecycle_score는 미래 생존 확률이 아닙니다.

분석 가능한 업종끼리 다음 요소를 이용하여
상대 비교한 개폐업 안정성 점수입니다.

- 최근 1년 폐업률 안정성
- 전체 분석기간 순증감률
- 전체 분석기간 회전 안정성
- 폐업률 변화 추세

따라서 다음 표현은 사용하면 안 됩니다.

잘못된 표현:
- "생존 확률이 74.5%입니다."
- "이 업종은 74.5% 확률로 살아남습니다."

올바른 표현:
- "개폐업 안정성 점수는 74.5점입니다."
- "분석 가능한 업종 가운데 상대적으로 안정적인 편입니다."

==================================================
[업종 Type]
==================================================

각 업종을 아래 네 가지 중 하나로 분류합니다.

1. 성장·안정형

특징:
- 순증감이 긍정적
- 최근 폐업률이 낮은 편
- 폐업률 추세가 유지 또는 개선
- 지나치게 높은 회전율을 보이지 않음

2. 안정 유지형

특징:
- 순증감 변화는 크지 않음
- 폐업률이 비교적 안정적
- 최근 상황이 크게 악화되지 않음
- 급격한 성장보다는 안정적으로 유지되는 업종

3. 과열·회전형

특징:
- 개업과 폐업이 모두 활발함
- turnover_rate가 상대적으로 높음
- 성장 신호가 있더라도 업종 교체가 빈번함
- 단순히 좋은 업종으로 해석해서는 안 됨

4. 쇠퇴·위험형

특징:
- 순증감이 부정적
- 최근 폐업률이 높은 편
- 폐업률이 과거보다 증가
- 또는 여러 위험 신호가 동시에 존재

==================================================
[Confidence]
==================================================

confidence는 다음과 같이 해석합니다.

high:
데이터 기간과 점포 규모가 충분하여 비교적 신뢰도가 높음

medium:
분석 가능하지만 표본 규모 또는 점포 수에 주의가 필요함

low:
점포 수가 적거나 데이터 규모가 작아 해석에 주의가 필요함

confidence가 low인 경우에는 warning에
표본 규모가 작다는 점을 반드시 언급하십시오.

==================================================
[Evidence 작성 규칙]
==================================================

각 업종마다 evidence를 2~3개 작성하십시오.

반드시 입력 데이터에 실제로 존재하는 수치를 근거로 작성하십시오.

좋은 예:

[
  "최근 1년 폐업률은 3.2%로 낮은 편입니다.",
  "최근 3년 동안 개업 18건, 폐업 11건으로 순증가했습니다.",
  "과거 대비 최근 폐업률이 2.1%p 감소했습니다."
]

나쁜 예:

[
  "앞으로 성공할 가능성이 높습니다.",
  "주변 수요가 많을 것으로 예상됩니다.",
  "유동인구가 많습니다."
]

입력 데이터에 없는 사실은 절대로 추론하지 마십시오.

==================================================
[Warning 작성 규칙]
==================================================

다음 경우 warning을 작성할 수 있습니다.

- confidence가 low
- 점포 수가 매우 적음
- 순증감은 좋지만 회전율이 매우 높음
- 일부 지표가 서로 상반된 신호를 보임

특별한 주의사항이 없으면 null을 사용하십시오.

==================================================
[출력 규칙]
==================================================

반드시 JSON만 출력하십시오.

Markdown 코드블록을 사용하지 마십시오.

입력에 존재하지 않는 업종을 새로 만들지 마십시오.

입력으로 전달된 모든 업종을 정확히 한 번씩 출력하십시오.

industry_id,
industry_name,
lifecycle_score,
confidence 값은 입력값을 변경하지 마십시오.

출력 형식:

{
  "summary": "전체 분석에 대한 짧은 설명",
  "industry_scores": [
    {
      "industry_id": 1,
      "industry_name": "한식음식점",
      "lifecycle_score": 68.4,
      "type": "성장·안정형",
      "confidence": "high",
      "evidence": [
        "근거 1",
        "근거 2",
        "근거 3"
      ],
      "warning": null
    }
  ]
}
"""


class BusinessLifecycleAgentError(RuntimeError):
    """Business Lifecycle Agent 실행 오류."""


def get_llm_client() -> OpenAI:
    """
    Elice OpenAI 호환 Client 생성.

    팀 공통 환경변수인 ELICE_API_KEY / ELICE_BASE_URL을 우선 사용하고,
    기존 로컬 환경과의 호환을 위해 ELICE_MLAPI_*도 fallback으로 지원합니다.
    """

    api_key = os.getenv("ELICE_API_KEY") or os.getenv("ELICE_MLAPI_KEY")
    base_url = os.getenv("ELICE_BASE_URL") or os.getenv("ELICE_MLAPI_BASE_URL")

    if not api_key:
        raise BusinessLifecycleAgentError(
            "ELICE_API_KEY 환경변수가 설정되어 있지 않습니다."
        )

    if not base_url:
        raise BusinessLifecycleAgentError(
            "ELICE_BASE_URL 환경변수가 설정되어 있지 않습니다."
        )

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def get_model_name() -> str:
    """팀 공통 ELICE_MODEL을 사용하고, 미설정 시 기존 모델을 사용합니다."""
    return os.getenv("ELICE_MODEL") or DEFAULT_MODEL_NAME


def clean_json_response(
    text: str,
) -> str:
    """
    혹시 LLM이 ```json 코드블록으로 감싸서 반환한 경우 제거.
    """

    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[
            len("```json"):
        ]

    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def parse_llm_response(
    response_text: str,
) -> dict[str, Any]:
    """
    LLM 응답을 JSON으로 변환.
    """

    cleaned = clean_json_response(
        response_text
    )

    try:
        parsed = json.loads(
            cleaned
        )

    except json.JSONDecodeError as exc:
        raise BusinessLifecycleAgentError(
            "LLM 응답을 JSON으로 변환하지 못했습니다."
        ) from exc

    if not isinstance(
        parsed,
        dict,
    ):
        raise BusinessLifecycleAgentError(
            "LLM 응답의 최상위 구조가 JSON 객체가 아닙니다."
        )

    return parsed


def validate_llm_result(
    agent_input: dict[str, Any],
    llm_result: dict[str, Any],
) -> None:
    """
    LLM이 입력으로 받은 모든 업종을
    정확히 반환했는지 확인.
    """

    input_industries = (
        agent_input["industries"]
    )

    output_industries = (
        llm_result.get(
            "industry_scores",
            [],
        )
    )

    input_ids = {
        industry["industry_id"]
        for industry
        in input_industries
    }

    output_ids = {
        industry.get("industry_id")
        for industry
        in output_industries
    }

    if input_ids != output_ids:
        missing = (
            input_ids - output_ids
        )

        extra = (
            output_ids - input_ids
        )

        raise BusinessLifecycleAgentError(
            "LLM 업종 결과가 입력과 일치하지 않습니다. "
            f"누락={sorted(missing)}, "
            f"추가={sorted(extra)}"
        )


def run_llm_analysis(
    agent_input: dict[str, Any],
) -> dict[str, Any]:
    """
    점수가 계산된 업종을 여러 batch로 나누어
    LLM에게 전달한다.

    LLM은 type / evidence / warning만 해석한다.
    """

    client = get_llm_client()

    industries = agent_input[
        "industries"
    ]

    all_industry_scores: list[
        dict[str, Any]
    ] = []

    # ========================================================
    # Batch 단위 LLM 호출
    # ========================================================

    for start in range(
        0,
        len(industries),
        BATCH_SIZE,
    ):
        batch = industries[
            start:start + BATCH_SIZE
        ]

        batch_number = (
            start // BATCH_SIZE
        ) + 1

        print()
        print(
            f"===== LLM Batch {batch_number} ====="
        )

        print(
            "분석 업종 수:",
            len(batch),
        )

        llm_input = {
            "scope": agent_input[
                "scope"
            ],

            "scoring_method": agent_input[
                "scoring_method"
            ],

            "industries": batch,
        }

        response = (
            client.chat.completions.create(
                model=get_model_name(),
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            llm_input,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    },
                ],
            )
        )

        choice = response.choices[0]

        print(
            "finish_reason:",
            choice.finish_reason,
        )

        response_text = (
            choice.message.content
        )

        if not response_text:
            raise BusinessLifecycleAgentError(
                f"LLM Batch {batch_number}의 "
                "응답 내용이 비어 있습니다. "
                f"finish_reason="
                f"{choice.finish_reason}"
            )

        batch_result = parse_llm_response(
            response_text
        )

        batch_scores = (
            batch_result.get(
                "industry_scores"
            )
        )

        if not isinstance(
            batch_scores,
            list,
        ):
            raise BusinessLifecycleAgentError(
                f"LLM Batch {batch_number}의 "
                "industry_scores가 올바르지 않습니다."
            )

        # ====================================================
        # 현재 batch의 ID 검증
        # ====================================================

        input_ids = {
            industry[
                "industry_id"
            ]
            for industry in batch
        }

        output_ids = {
            industry.get(
                "industry_id"
            )
            for industry in batch_scores
        }

        if input_ids != output_ids:
            missing = (
                input_ids - output_ids
            )

            extra = (
                output_ids - input_ids
            )

            raise BusinessLifecycleAgentError(
                f"LLM Batch {batch_number} "
                "업종 결과 불일치. "
                f"누락={sorted(missing)}, "
                f"추가={sorted(extra)}"
            )

        all_industry_scores.extend(
            batch_scores
        )

        print(
            f"Batch {batch_number} 완료"
        )

    # ========================================================
    # 전체 결과 구성
    # ========================================================

    llm_result: dict[str, Any] = {
        "summary": (
            f"최근 {agent_input['scope']['period']['quarter_count']}개 "
            f"분기의 개폐업 데이터를 기반으로 "
            f"{len(all_industry_scores)}개 업종을 분석했습니다."
        ),

        "industry_scores":
            all_industry_scores,
    }

    # ========================================================
    # 최종 50개 전체 검증
    # ========================================================

    validate_llm_result(
        agent_input=agent_input,
        llm_result=llm_result,
    )

    return llm_result


def run_business_lifecycle_agent(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
    request_id: str | None = None,
    area_name: str | None = None,
) -> dict[str, Any]:
    """
    Business Lifecycle 전체 파이프라인 실행.

    Open API
    → 전처리
    → 점수 계산
    → Agent Input
    → LLM 해석
    """

    # ========================================================
    # 1. Agent Input 생성
    # ========================================================

    agent_input = build_agent_input(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        request_id=request_id,
        area_name=area_name,
    )

    # ========================================================
    # 2. 점수가 있는 업종만 LLM 분석
    # ========================================================

    llm_result = run_llm_analysis(
        agent_input=agent_input
    )

    # ========================================================
    # 3. 최종 Agent 결과 생성
    # ========================================================

    result: dict[str, Any] = {
        "request_id": agent_input[
            "request_id"
        ],

        "agent_id":
            "business_lifecycle",

        "scope": agent_input[
            "scope"
        ],

        "coverage": agent_input[
            "coverage"
        ],

        "scoring_method": agent_input[
            "scoring_method"
        ],

        "summary": llm_result.get(
            "summary",
            "",
        ),

        # LLM 분석 완료 업종
        "industry_scores": (
            llm_result[
                "industry_scores"
            ]
        ),

        # 데이터 부족으로 판단 보류
        "unavailable_industries": (
            agent_input[
                "unavailable_industries"
            ]
        ),
    }

    return result


async def analyze(
    task: AnalysisTask | dict,
    settings: Settings | None = None,
    area_resolver: ResolveArea | None = None,
    run_pipeline: RunPipeline | None = None,
) -> AgentAnalysis:
    """팀 공통 인터페이스로 Business Lifecycle 분석을 실행합니다."""
    load_dotenv_if_present()
    task = AnalysisTask.model_validate(task)
    settings = settings or Settings.from_env()
    return await asyncio.to_thread(
        _analyze_sync,
        task,
        settings,
        area_resolver or resolve_area,
        run_pipeline or _run_pipeline,
    )


def _analyze_sync(
    task: AnalysisTask,
    settings: Settings,
    area_resolver: ResolveArea,
    run_pipeline: RunPipeline,
) -> AgentAnalysis:
    site = task.site

    try:
        area = _resolve_area(
            site=site,
            settings=settings,
            area_resolver=area_resolver,
        )
        base_quarter = _choose_base_quarter(
            area_code=area.area_code,
            settings=settings,
        )
        agent_result = run_pipeline(
            area.area_code,
            base_quarter,
            settings.quarter_count,
            task.request_id,
            area.area_name,
        )
        return format_for_mediator(
            agent_result,
            scope_area=f"{area.area_name} ({area.area_code})",
            scope_period=_period_label(agent_result),
            metadata={
                "area_code": area.area_code,
                "area_name": area.area_name,
                "area_type_code": area.area_type_code,
                "area_type_name": area.area_type_name,
                "district_code": area.district_code,
                "district_name": area.district_name,
                "dong_code": area.dong_code,
                "dong_name": area.dong_name,
                "base_quarter": base_quarter,
                "quarter_count": settings.quarter_count,
                "area_resolver": {
                    "method": (
                        "env_override" if _has_area_override(settings) else "official_polygon"
                    ),
                    "distance_m": round(area.distance_m, 1),
                    "coordinate_system": "EPSG:5181",
                },
            },
            extra_warnings=[area.warning],
        )
    except (BusinessAreaNoDataError, BusinessAreaResolverError) as exc:
        return _no_data(
            task=task,
            area=site.input_address,
            period="서울시 상권영역",
            warning=str(exc),
        )
    except SeoulOpenAPINoDataError as exc:
        return _no_data(
            task=task,
            area=site.input_address,
            period="서울시 최신 유효 분기",
            warning=str(exc),
        )
    except FutureQuarterError as exc:
        return _error(task, "INVALID_INPUT", exc)
    except ValueError as exc:
        if _is_no_data_error(exc):
            return _no_data(
                task=task,
                area=site.input_address,
                period="서울시 점포 개폐업 데이터",
                warning=str(exc),
            )
        return _error(task, "INVALID_INPUT", exc)
    except (SeoulOpenAPIError, BusinessLifecycleAgentError, BusinessLifecycleFormatterError) as exc:
        return _error(task, type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001
        return _error(task, "AGENT_FAILED", exc)


def _resolve_area(
    *,
    site: Site,
    settings: Settings,
    area_resolver: ResolveArea,
) -> BusinessArea:
    if settings.area_code_override or settings.area_name_override:
        if not settings.area_code_override or not settings.area_name_override:
            raise ValueError(
                "BUSINESS_LIFECYCLE_AREA_CODE와 BUSINESS_LIFECYCLE_AREA_NAME은 "
                "함께 설정해야 합니다."
            )
        return BusinessArea(
            area_code=settings.area_code_override,
            area_name=settings.area_name_override,
            area_type_code=None,
            area_type_name=None,
            district_code=None,
            district_name=None,
            dong_code=None,
            dong_name=None,
            x=0.0,
            y=0.0,
            distance_m=0.0,
            warning="환경변수로 지정한 상권을 사용했습니다.",
        )

    return area_resolver(site, settings)


def _has_area_override(settings: Settings) -> bool:
    return bool(settings.area_code_override and settings.area_name_override)


def _run_pipeline(
    area_code: str,
    base_quarter: str,
    quarter_count: int,
    request_id: str | None,
    area_name: str | None,
) -> dict[str, Any]:
    return run_business_lifecycle_agent(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        request_id=request_id,
        area_name=area_name,
    )


def _choose_base_quarter(
    area_code: str,
    settings: Settings,
) -> str:
    if settings.base_quarter_override:
        from .client import compare_quarters, latest_closed_quarter, validate_quarter_code

        validate_quarter_code(settings.base_quarter_override)
        if compare_quarters(settings.base_quarter_override, latest_closed_quarter()) > 0:
            raise FutureQuarterError(
                f"아직 확정되지 않은 분기는 조회하지 않습니다: "
                f"{settings.base_quarter_override}"
            )
        return settings.base_quarter_override

    return detect_latest_valid_quarter(
        area_code=area_code,
        candidate_count=settings.latest_quarter_search_count,
    )


def _period_label(agent_result: dict[str, Any]) -> str:
    scope = agent_result.get("scope", {})
    period = scope.get("period", {})
    if isinstance(period, dict):
        start = period.get("start_quarter")
        end = period.get("end_quarter")
        count = period.get("quarter_count")
        if start and end and count:
            return f"{start}~{end} ({count}개 분기)"
    base_quarter = scope.get("base_quarter")
    if base_quarter:
        return str(base_quarter)
    return "기준 기간 확인 불가"


def _is_no_data_error(exc: ValueError) -> bool:
    return "조회된 데이터가 없습니다" in str(exc)


def _no_data(
    *,
    task: AnalysisTask,
    area: str,
    period: str,
    warning: str,
) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        status="no_data",
        scope=Scope(area=area, period=period),
        warnings=[warning],
    )


def _error(
    task: AnalysisTask,
    code: str,
    exc: BaseException,
) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=AGENT_ID,
        status="error",
        error=AgentError(
            code=code,
            message=f"{type(exc).__name__}: {exc}"[:500],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Business Lifecycle Agent 실행"
        )
    )

    parser.add_argument(
        "--area-code",
        required=True,
        help="서울시 상권코드",
    )

    parser.add_argument(
        "--base-quarter",
        required=True,
        help="기준 분기. 예: 20252",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="분석 분기 수. 기본값 12",
    )

    parser.add_argument(
        "--output",
        help=(
            "테스트용 Agent 결과 JSON 저장 경로"
        ),
    )

    parser.add_argument(
    "--request-id",
    help=(
        "외부에서 전달받은 요청 ID. "
        "생략하면 테스트용 ID가 자동 생성됩니다."
        ),
    )

    args = parser.parse_args()

    result = (
        run_business_lifecycle_agent(
            area_code=args.area_code,
            base_quarter=args.base_quarter,
            quarter_count=args.count,
            request_id=args.request_id,
        )
    )

    print()
    print(
        "===== Business Lifecycle Agent 완료 ====="
    )

    print(
        "분석 업종:",
        len(
            result[
                "industry_scores"
            ]
        ),
    )

    print(
        "판단 보류 업종:",
        len(
            result[
                "unavailable_industries"
            ]
        ),
    )

    print(
        "요약:",
        result["summary"],
    )

    if args.output:
        output_path = Path(
            args.output
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print(
            "Agent 결과 저장 완료:",
            output_path,
        )


if __name__ == "__main__":
    main()
