"""유동인구 분석 결과의 자료 구조.

`AgentAnalysis.data` 는 계약상 자유 형식 JSON 이지만, 결정 에이전트가 근거를 JSON Pointer
경로(`Evidence.path`, 예: `/benchmark/lunch_index`)로 가리키기 때문에 **키 구조가 사실상
인터페이스다.** 자유 형식 dict 로 두면 여기서 키 하나 바꿀 때 결정 쪽 검증이 조용히 깨진다.
그래서 모델로 고정하고, 키를 바꿀 때는 결정 에이전트 담당과 함께 바꾼다.

리포트 에이전트도 같은 `data` 로 차트·표를 만든다(결정 에이전트가 `source_analyses` 에
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

    ⚠️ 인원수는 모두 **분기 합계**다(원본 데이터가 그렇다 — `by_day` 합계가 `total` 과 같은
    것으로 확인). 같은 사람의 반복 통행이 중복 집계되고, **하루 평균이 아니다.** 결정
    에이전트가 다른 에이전트의 "명/일" 수치와 헷갈리지 않게 `unit` 과 `daily_avg` 를 함께 싣는다.
    """

    unit: Text
    share_unit: Text

    total: float
    daily_avg: float  # total ÷ 분기 일수. 다른 에이전트의 "명/일" 과 비교 가능한 값
    male: float
    female: float
    female_ratio: float

    by_age: dict[str, float]
    age_share: dict[str, float]

    by_time: dict[str, float]
    # 시간대 비교는 반드시 이 값으로 한다 — 구간 길이가 3~6시간으로 달라서 총량으로 비교하면
    # 6시간짜리 00~06시가 거의 항상 1위가 된다(실데이터에서 확인된 왜곡).
    time_per_hour_share: dict[str, float]
    peak_time_band: Text

    by_day: dict[str, float]
    # 이름을 `*_daily_avg` 로 두었더니 "하루 평균" 으로 읽혔다. 실제로는 분기 중 해당 요일
    # 합계들의 평균이라 하루 평균의 13배쯤 된다. 하루 평균은 위 `daily_avg` 를 쓴다.
    weekday_avg: float
    weekend_avg: float
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

    mean_per_trade_area: float
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
    trade_areas: list[TradeArea]
    population: Population
    benchmark: Benchmark
    type: TypeJudgement
    reliability: Reliability
    sources: list[Source]
