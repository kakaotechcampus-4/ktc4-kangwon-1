"""유동인구 분석 결과의 자료 구조.

`AgentAnalysis.data` 는 계약상 자유 형식 JSON 이지만, 결정 에이전트가 근거를 JSON Pointer
경로(`Evidence.path`, 예: `/benchmark/lunch_index`)로 가리키기 때문에 **키 구조가 사실상
인터페이스다.** 자유 형식 dict 로 두면 여기서 키 하나 바꿀 때 결정 쪽 검증이 조용히 깨진다.
그래서 모델로 고정하고, 키를 바꿀 때는 결정 에이전트 담당과 함께 바꾼다.

화면도 같은 `data` 로 차트·표를 만든다(최종판단이 `source_analyses` 에
그대로 실어 보낸다). 그래서 판단용 지표(`benchmark`)와 차트용 원시 시리즈(`population`)를
둘 다 담는다.
"""

from __future__ import annotations

from typing import Literal

from app.schemas import Schema, Text


class TradeArea(Schema):
    """집계에 포함된 상권 하나.

    `distance_m` 은 입력 좌표에서 상권 **대표 점**까지의 거리다. 상권은 점이 아니라 구역이므로
    크기(`area_m2`·`equivalent_radius_m`)를 함께 싣는다 — `distance_m` 만 보면 큰 상권이
    왜 포함됐는지 설명이 안 된다.
    """

    code: Text
    name: Text
    kind: Text | None = None  # 골목상권 · 발달상권 · 전통시장 등
    adstrd: Text | None = None
    distance_m: float
    area_m2: float
    equivalent_radius_m: float


class Population(Schema):
    """반경 안 상권을 합산한 유동인구 분포. 리포트 차트·표의 원본이다.

    **인원수는 `daily_avg`(명/일) 하나로만 낸다.** 원본은 분기 합계인데, 그걸 그대로 실으면
    다른 에이전트의 "명/일" 과 나란히 놓였을 때 1,000배로 오독된다(목업 유동인구가
    `daily_average: 15,200명/일` 이었다). 합계·남녀 인원수·요일 평균은 쓸 곳이 없으면서
    오독 위험만 있어 아예 내보내지 않는다 — 필요한 형태(비율·일평균)로만 낸다.

    분기 합계 원값이 남아 있는 곳은 아래 `by_age`·`by_time`·`by_day` 뿐이고, 그 셋은
    `population_raw` 로 묶여 선별 대상이다.
    """

    unit: Text
    share_unit: Text

    daily_avg: float  # 분기 합계 ÷ 분기 일수. 다른 에이전트의 "명/일" 과 비교 가능한 값
    female_ratio: float

    # 원본은 선별과 무관하게 보존합니다. 최종판단 입력 복사본에서만 이 셋을 제외할 수 있습니다.
    # 기존 저장 자료를 읽을 수 있도록 nullable 계약은 유지합니다.
    by_age: dict[str, float] | None
    age_share: dict[str, float]

    by_time: dict[str, float] | None
    # 시간대 비교는 반드시 이 값으로 한다 — 구간 길이가 3~6시간으로 달라서 총량으로 비교하면
    # 6시간짜리 00~06시가 거의 항상 1위가 된다(실데이터에서 확인된 왜곡).
    time_per_hour_share: dict[str, float]
    peak_time_band: Text

    by_day: dict[str, float] | None
    # 주중·주말 평균 인원수는 내보내지 않는다. 한때 `weekday_daily_avg` 로 두었더니 "하루
    # 평균" 으로 읽혔는데 실제로는 분기 중 해당 요일 합계들의 평균이라 하루 평균의 13배였다.
    # 쓸 곳은 이 비율뿐이라 비율만 낸다.
    weekend_to_weekday_ratio: float


class Benchmark(Schema):
    """서울 평균 대비 상대지표. 1.0 이 평균.

    결정 에이전트가 점수를 계산하고 근거 문장을 쓰는 자리다. 절대 비중만 주면 판단이 안 된다 —
    시간대는 구간이 6개라 균등값이 0.167 이고, 0.16 이 높은지 낮은지 알 수 없다.
    """

    unit: Text
    baseline: Text
    age_index: dict[str, float]
    time_per_hour_index: dict[str, float]

    lunch_index: float  # 11~14시
    evening_index: float  # 17~21시
    night_index: float  # 21~24시
    weekend_index: float

    # 상권 1곳당 일평균. 분기 합계로 두면 블록 unit("배수")과 어긋나고 오독 위험도 남는다.
    mean_daily_per_trade_area: float
    scale_percentile: int  # 서울 상권 중 규모 백분위(상권 1곳당 기준)


class TypeJudgement(Schema):
    """유동인구 유형 — 결정론적 규칙(LLM 아님). 같은 입력이면 항상 같은 결과."""

    label: Text
    is_inference: bool
    signals_unit: Text
    reasons: list[Text]
    # 판정에 쓴 숫자를 그대로 남긴다. 결정 에이전트가 문장이 아니라 값을 인용할 수 있도록.
    signals: dict[str, float]
    thresholds: dict[str, float]
    rules_version: Text


class Reliability(Schema):
    """이 분석을 얼마나 믿을 수 있는지. 결정 에이전트가 가중치를 낮추는 근거다.

    warnings 문장으로만 주면 결정 쪽이 코드로 읽을 수 없어서 숫자로도 낸다.
    """

    trade_area_count: int
    covered_trade_areas: int
    level: Literal["high", "medium", "low"]


class QuarterPoint(Schema):
    """추세 그래프의 점 하나 = 한 분기.

    같은 상권 집합을 분기마다 다시 합산한 값이다. 분기별로 상권 목록이 조금씩 바뀌므로
    (서울 전체 1,648~1,650곳 사이에서 오르내린다) 그 분기에 실제로 자료가 있던 상권 수를
    `trade_area_count` 로 함께 싣는다 — 이 값이 흔들리면 증감이 상권 수 변화일 수 있다.
    """

    period_code: Text  # "20262"
    period: Text  # "2026년 2분기"
    # 분기 합계는 싣지 않는다 — 분기 일수(90~92일)가 달라 그대로 비교하면 가짜 증감이 섞이고,
    # 비교에 쓸 수 있는 형태는 일평균뿐이다.
    daily_avg: float
    trade_area_count: int
    age_share: dict[str, float]
    time_per_hour_share: dict[str, float]


class Trend(Schema):
    """분기별 추세. 최신 1개 분기만 보던 단면 분석의 한계를 푼다.

    `quarters` 는 **오래된 순**이라 그대로 꺾은선 차트의 x축이 된다.
    """

    unit: Text
    quarters: list[QuarterPoint]
    # 최신 vs 직전 분기. 분기가 2개 미만이면 None.
    qoq_change: float | None = None
    # 최신 vs 4분기 전(전년 동기). 계절성을 제거한 비교라 판단에는 이쪽이 낫다.
    # 분기가 5개 미만이면 None.
    yoy_change: float | None = None
    direction: Text  # "증가" · "감소" · "보합" · "판단 불가"


class RadiusPoint(Schema):
    """분석 반경 안쪽을 나눠 본 지점 하나.

    `daily_avg` 는 그 반경 안에 **면적 안분으로 들어온 몫**이다. 상권 전체가 아니라
    겹친 면적 비율만큼만 센다.
    """

    radius_m: int
    total: float
    daily_avg: float
    # 조금이라도 걸친 상권 수(안분 가중치 > 0). 반경 안에 통째로 든 상권 수가 아니다.
    trade_area_count: int
    # 안분 가중치의 합. 상권 "몇 곳분" 인지를 뜻한다(예: 2.4 = 상권 2.4곳분).
    effective_trade_areas: float


class RadiusProfile(Schema):
    """분석 반경(500m) 안쪽을 단계별로 나눠 본 인구.

    ⚠️ 원자료가 **상권 조각 단위**라 개수로 세면 작은 반경에서 성립하지 않는다. 대표 점이
    반경 안에 든 상권 수를 실측하니 300m 아래에서 네 지점 모두 0~1곳이었다(길동·서교동·
    평창동은 200m 까지 0곳). 그래서 계산을 **면적 단위**로 한다 — 겹친 면적 비율만큼만 센다.
    가정("상권 안 인구가 고르게 분포")은 `method` 에 밝혀 둔다.
    """

    unit: Text
    method: Text
    points: list[RadiusPoint]


class Selection(Schema):
    """최종판단 입력에 넣을 블록. 원본 반환·저장에는 영향을 주지 않습니다.

    최종판단이 직렬화한 입력 복사본에만 선택을 적용합니다. 배열 일부를 압축하지 않아
    남아 있는 근거 경로는 원본에서도 같은 값을 가리킵니다.

    **선별은 최적화지 기능이 아니다.** 모델이 없거나 실패하면 `applied=False` 로 전부 싣는다 —
    분석 자체는 그대로 나가야 한다.
    """

    applied: bool
    selectable: list[Text]  # 고를 수 있었던 블록 전부
    included: list[Text]
    dropped: list[Text]
    # 뺀 이유(사람이 읽는 문장). 뺀 것이 없거나 선별을 못 했으면 `null`.
    # (팀 `Text` 는 빈 문자열을 막으므로 "없음" 은 `null` 로 나타낸다)
    reason: Text | None = None
    # 선별을 못 한 이유. `applied=True` 면 `null`.
    unavailable_reason: Text | None = None


class Source(Schema):
    name: Text
    url: Text
    license: Text
    period: Text


class FloatingPopulationData(Schema):
    """`AgentAnalysis.data` 에 실리는 본문.

    맨 앞에 `description` 을 둔다 — 결정 에이전트 프롬프트가 "필드 이름, 설명, 단위와 실제
    값을 함께 읽는다" 고 명시하고 있어서, 숫자의 기준(분기 합계인지 일평균인지)을 글로도
    밝혀 두지 않으면 오독된다.
    """

    description: Text
    period_code: Text
    radius_m: int
    # 과거 저장 자료의 null은 허용하되, 새 분석은 선별 전 원본을 보존합니다.
    trade_areas: list[TradeArea] | None
    population: Population
    benchmark: Benchmark
    trend: Trend | None
    radius_profile: RadiusProfile | None
    type: TypeJudgement
    reliability: Reliability
    selection: Selection
    sources: list[Source]
