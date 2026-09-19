export interface RecommendedIndustry {
  rank: number;
  name: string;
  score: number;
  tags: string[];
}

export interface FootTrafficHourly {
  hour: string; // "00시", "06시" 등
  count: number;
}

export interface AgeGroupData {
  label: string; // "10대", "20대" 등
  percent: number;
}

export interface CompetitorData {
  industry: string;
  count: number;
  recommended: boolean;
}

export interface OpenCloseQuarter {
  quarter: string; // "2025 Q1" 등
  opened: number;
  closed: number;
}

export type AgentStatus = 'ok' | 'partial' | 'no_data' | 'error';

/**
 * 개폐업(business_lifecycle) 에이전트 원본 스키마.
 *
 * 지난 버전은 backend/app/agents/business_lifecycle/business_lifecycle_agent_output.json
 * (예전 설계 단계 예시 파일)을 기준으로 만들었는데, 실제로 AgentAnalysis.data를
 * 만드는 코드(feature/mvp1-refact 브랜치의 input_builder.py의
 * build_agent_input() → formatter.py의 format_for_mediator())를 직접 추적한
 * 결과 구조가 전혀 다름을 확인했다. 그 예시 파일은 지금도 저장소에 그대로
 * 남아 있지만(backend/examples/fixtures/business_lifecycle_agent_output.json),
 * 코드가 실제로 만드는 값과 안 맞는 stale한 문서다 — 아래는 코드를 기준으로
 * 다시 옮긴 것이다. 필드명은 camelCase로 바꾸지 않고 원본 snake_case를
 * 그대로 쓴다(commercial_area와 달리, 이 에이전트는 화면에 쓸 문장(evidence)·
 * 배지 라벨(type)까지 이미 만들어 내려준다).
 */
export type BusinessLifecycleConfidence = 'high' | 'medium' | 'low' | 'none';

// input_builder.py의 preprocess 단계(row["data_status"])가 매기는 값 4종.
// unsupported: 서울시 생활밀접업종에 대응 항목 자체가 없음
// missing: 대응 항목은 있지만 최근 분기에 관측된 자료가 없음
// incomplete: 일부 분기·원천업종이 빠져 완전 집계가 안 됨
// observed: 정상 관측
export type BusinessLifecycleDataStatus =
  'observed' | 'unsupported' | 'missing' | 'incomplete';

/**
 * 점수 계산 업종은 17개 필드가 전부 채워지고, 판단 보류 업종은 이 중
 * 11개(observed_quarters·recent_year_open_count·recent_year_close_count·
 * recent_year_net_change·recent_year_net_change_rate·oldest_year_close_rate
 * 제외)만 온다 — input_builder.py의 build_agent_input()에서 두 그룹의 metrics
 * 딕셔너리를 서로 다른 키 집합으로 만든다. 그래서 전부 optional + nullable로
 * 둔다(pandas NaN은 JSON null로 변환된다).
 */
export interface BusinessLifecycleMetrics {
  observed_quarters?: number | null;
  latest_store_count?: number | null;
  avg_store_count?: number | null;
  period_open_count?: number | null;
  period_close_count?: number | null;
  period_net_change?: number | null;
  avg_open_rate?: number | null;
  avg_close_rate?: number | null;
  net_change_rate?: number | null;
  turnover_rate?: number | null;
  recent_year_open_count?: number | null;
  recent_year_close_count?: number | null;
  recent_year_net_change?: number | null;
  recent_year_close_rate?: number | null;
  recent_year_net_change_rate?: number | null;
  oldest_year_close_rate?: number | null;
  close_rate_trend?: number | null;
}

/**
 * 판단 보류 업종에만 있다. formatter.py의 format_unscored_industry()가
 * input_builder.py가 만든 source_coverage(expected_source_count/
 * observed_source_rows/expected_source_rows)에 observed_quarters를
 * 합쳐 넣는다 — 그래서 이 네 필드가 실제로는 한 객체에 같이 들어온다.
 */
export interface BusinessLifecycleSourceCoverage {
  expected_source_count?: number | null;
  observed_source_rows?: number | null;
  expected_source_rows?: number | null;
  observed_quarters?: number | null;
}

export interface BusinessLifecycleIndustryResult {
  // input_builder.py: industry_id = str(row["service_id"]) — 소상공인
  // 상권업종 중분류 공통 코드(예: "I201"). 숫자가 아니라 문자열이다.
  industry_id: string;
  industry_name: string;
  // 판단 보류 업종은 null("판단 보류"). lifecycle_score가 아니라 score다.
  score: number | null;
  type: string;
  confidence: BusinessLifecycleConfidence;
  data_available: boolean;
  score_available: boolean;
  data_status?: BusinessLifecycleDataStatus;
  data_complete?: boolean;
  metrics: BusinessLifecycleMetrics;
  // 점수 계산 업종에는 없다("판단보류 업종만" — formatter.py가 이 필드를
  // score_available: true인 쪽에는 아예 안 만든다).
  source_coverage?: BusinessLifecycleSourceCoverage;
  evidence: string[];
  warning: string | null;
}

// formatter.py: coverage = {target_industries, scored_industries,
// unscored_industries} — available_industries/analyzed_industries 같은
// 필드는 없다.
export interface BusinessLifecycleCoverage {
  target_industries: number;
  scored_industries: number;
  unscored_industries: number;
}

/**
 * input_builder.py의 scoring.py 가중치(RECENT_CLOSE_RATE_WEIGHT=0.35 ·
 * NET_CHANGE_WEIGHT=0.25 · TURNOVER_WEIGHT=0.20 · CLOSE_TREND_WEIGHT=0.20)를
 * 그대로 옮긴 4개 필드다. 예전 버전은 3개(close_rate/net_change_rate/
 * turnover_stability)로 잘못 알고 있었다 — close_rate_trend(폐업률 변화
 * 추세)가 실제로는 네 번째 축이고, close_rate 자체가 아니라
 * recent_year_close_rate(최근 1년 폐업률)를 본다.
 */
export interface BusinessLifecycleScoringWeights {
  recent_year_close_rate: number;
  net_change_rate: number;
  turnover_stability: number;
  close_rate_trend: number;
}

export interface BusinessLifecycleScoringMethod {
  description: string;
  score_type: string;
  weights: BusinessLifecycleScoringWeights;
  notes: string[];
}

/**
 * 추천/비추천 10개 업종으로 이미 필터링된 결과.
 * lib/api/adapters/businessLifecycle.ts의 adaptBusinessLifecycle()이
 * industries(공통 업종 코드 75개) 중 이름이 일치하는 것만 골라 이 형태로
 * 만든다 — coverage/scoring_method는 필터링 없이 원본 그대로다.
 *
 * summary/metadata/taxonomy는 실제 응답에 있지만 화면이 아직 쓰지 않는다
 * (summary는 요약 카드 첫 줄로 보여주는 정도만 — CoverageSummary 참고).
 * 내부 구조가 화면 로직에 영향을 주지 않아 굳이 세부 타입을 만들지 않고
 * 느슨하게 둔다. metadata/taxonomy 필드가 실제로 필요해지면 그때 구체화한다.
 *
 * 최상위 "overall"(상권 전체 개업/폐업 합계)은 실제 데이터에 없어서
 * 삭제했다 — 필요해지면 industries 배열을 순회해 프론트에서 직접
 * 합산해야 한다(지금은 범위 밖).
 */
export interface BusinessLifecycleData {
  summary?: string;
  metadata?: Record<string, unknown>;
  coverage: BusinessLifecycleCoverage;
  taxonomy?: Record<string, unknown>;
  scoring_method: BusinessLifecycleScoringMethod;
  industries: BusinessLifecycleIndustryResult[];
}

/**
 * 경쟁업체(commercial_area) 에이전트 원본 스키마
 * (backend/app/agents/commercial_area/schemas.py) 중 화면에 노출 가능한
 * 필드만 옮겼다. 아래는 의도적으로 제외했다:
 *   - density_sq, marshallian, jacobian: 내부 판단용 지표, 사용자 노출 금지
 *   - by_middle 75종 전체: 대신 이미 순위가 잘린 by_radius[].top_by_count /
 *     district_specialization만 쓰고, B섹션(업종별 카드)에만 name 매칭용으로
 *     제한된 10개 항목만 별도로 둔다.
 */
export interface CommercialAreaMajorCategory {
  code: string;
  name: string;
  count: number;
  share: number;
  densityPerKm2: number;
}

export interface CommercialAreaCategoryRank {
  rank: number;
  code: string;
  name: string;
  count: number;
  densityPerKm2: number;
  note: string; // 백엔드가 이미 완성 문장으로 내려주는 캡션. 그대로 노출한다.
}

export interface CommercialAreaSpecializationRank {
  rank: number;
  code: string;
  name: string;
  count: number;
  timesVsSurroundings: number;
  note: string;
}

export interface CommercialAreaRadiusSlice {
  radiusM: number;
  storeTotal: number;
  categoryCount: number;
  absentCategoryCount: number;
  topByCount: CommercialAreaCategoryRank[];
}

export interface CommercialAreaDiversity {
  effectiveCategories: number;
}

export interface CommercialAreaFranchise {
  count: number;
  ratio: number;
  confidence: 'low' | 'medium' | 'high';
}

export interface CommercialAreaLqBaseline {
  requestedRadiusM: number;
  appliedRadiusM: number | null;
}

export interface CommercialAreaDistrictBaseline {
  signguName: string;
}

/**
 * B섹션(추천·비추천 10개 업종별 경쟁 지표)용, by_middle에서 이 리포트가
 * 다루는 10개 업종에 해당하는 항목만 미리 골라둔 것. 실제 연동 시에는
 * commercial_area 응답의 by_middle 배열 전체를 받아 아래 매핑 테이블
 * (RECOMMENDED_NAME_TO_MIDDLE_CODE, 이 파일 하단)로 code 매칭한다.
 *
 * lq / lqDistrict는 반드시 `=== null`로만 판별한다:
 *   - null: 비교 기준 자체가 없음(2km/자치구 baseline에 이 업종 표본이
 *     없거나 baseline을 못 구함) → "비교 불가"
 *   - 0.0: 비교는 가능하지만 이 반경에 해당 업종 점포가 0개라 배수가
 *     실제로 0 → "0.0배"로 그대로 표시 (null과 다른 값이므로 절대
 *     같은 문구로 뭉뚱그리지 않는다)
 */
export interface CommercialAreaMiddleCategory {
  code: string;
  name: string;
  sameTypeCount: number;
  diffTypeCount: number;
  lq: number | null;
  lqDistrict: number | null;
}

export interface CommercialAreaData {
  status: AgentStatus;
  errorMessage?: string;
  warnings: string[];
  radiusM: number;
  storeTotal: number;
  dataReferenceDate: string; // 이미 "OO일 조회" 형태 문자열. "자료 기준일"이라고 다시 라벨링하지 않는다.
  byMajor: CommercialAreaMajorCategory[];
  byRadius: CommercialAreaRadiusSlice[];
  diversity: CommercialAreaDiversity;
  franchise: CommercialAreaFranchise | null;
  lqBaseline: CommercialAreaLqBaseline;
  districtBaseline: CommercialAreaDistrictBaseline | null;
  districtSpecialization: CommercialAreaSpecializationRank[];
  byMiddleForRecommendations: CommercialAreaMiddleCategory[];
}

/**
 * 유동인구(floating_population) 에이전트 원본 스키마
 * (backend/app/agents/floating_population/schemas.py, develop 최신 기준) 중
 * 화면에 노출 가능한 필드만 옮겼다. business_lifecycle과 같은 이유로 필드명을
 * camelCase로 바꾸지 않고 snake_case 원본 그대로 쓴다 — 이 에이전트는 자체
 * 필드 구조가 곧 결정 에이전트의 JSON Pointer 인터페이스라(스키마 파일 상단
 * 주석 참고), 화면이 임의로 이름을 바꿔 옮기면 백엔드 쪽 변경을 조용히
 * 놓치기 쉽다.
 *
 * 아래는 의도적으로 제외했다:
 *   - population.by_time, by_age, by_day: 분기 합계 원값. by_time은 구간
 *     길이가 3~6시간으로 달라 원값을 그대로 비교하면 "새벽에 사람이 가장
 *     많다"는 틀린 결론이 난다(반드시 time_per_hour_share만 쓴다). by_day는
 *     비중 필드가 없어 요일 차트 자체를 이번 구현에서 스킵했다(팀 결정 필요).
 *   - type.signals, thresholds, rules_version, signals_unit: 판정 내부값,
 *     사용자 노출 금지.
 *   - data.description, period_code, population.unit/share_unit,
 *     benchmark.unit/baseline: 기계 판독·LLM 프롬프트용 문자열, 화면 비표시.
 *   - benchmark.time_per_hour_index, mean_daily_per_trade_area: 지금 화면이
 *     쓰는 지표(연령/시간대/규모)에 없어 제외.
 *   - trade_areas의 code, distance_m, area_m2, equivalent_radius_m, adstrd:
 *     내부 판정용. name/kind만 남겼다.
 *   - trend.unit, yoy_change / radius_profile.unit / selection.selectable,
 *     included, unavailable_reason: 화면이 쓰는 최소 필드만 남겼다.
 *
 * trend/radius_profile/selection은 과거 "백엔드 미구현" 상태였지만 이제
 * 실제 스키마에 전부 구현돼 있다(develop 기준 재확인 완료).
 */
export type ReliabilityLevel = 'high' | 'medium' | 'low';
// "판단 불가"는 분기가 2개 미만이라 direction 자체를 못 정할 때 나온다
// (backend/app/agents/floating_population/schemas.py의 Trend.direction 주석).
export type TrendDirection = '증가' | '감소' | '보합' | '판단 불가';

export interface FloatingPopulationTradeArea {
  name: string;
  kind: string | null;
}

export interface FloatingPopulationPopulation {
  daily_avg: number;
  female_ratio: number;
  age_share: Record<string, number>; // key: '10'|'20'|...|'60' ("60"은 60대+로 라벨링)
  time_per_hour_share: Record<string, number>; // key: '00_06' 등, 반드시 이 필드만 사용
  peak_time_band: string;
  weekend_to_weekday_ratio: number;
}

export interface FloatingPopulationBenchmark {
  age_index: Record<string, number>; // 서울 평균 대비 배수(1.0 기준)
  lunch_index: number;
  evening_index: number;
  night_index: number;
  weekend_index: number;
  scale_percentile: number; // 서울 상권 중 규모 백분위
}

export interface FloatingPopulationType {
  label: string;
  reasons: string[];
  is_inference: boolean;
}

export interface FloatingPopulationReliability {
  trade_area_count: number;
  covered_trade_areas: number;
  level: ReliabilityLevel;
}

export interface FloatingPopulationSource {
  name: string;
  license: string;
  period: string;
}

export interface FloatingPopulationTrendQuarter {
  period: string;
  daily_avg: number;
}

export interface FloatingPopulationTrend {
  quarters: FloatingPopulationTrendQuarter[];
  direction: TrendDirection;
  qoq_change: number | null; // 분기가 2개 미만이면 null(backend 스키마 그대로).
}

export interface FloatingPopulationRadiusPoint {
  radius_m: number;
  daily_avg: number;
}

export interface FloatingPopulationRadiusProfile {
  points: FloatingPopulationRadiusPoint[];
  method: string;
}

export interface FloatingPopulationSelection {
  applied: boolean;
  dropped: string[]; // 예: ['trend', 'radius_profile'] — 어떤 하위 분석이 생략됐는지
  reason: string | null; // 뺀 것이 없거나 선별을 못 했으면 null(backend 스키마 그대로).
}

export interface FloatingPopulationData {
  status: AgentStatus;
  errorMessage?: string;
  warnings: string[];
  radius_m: number;
  trade_areas: FloatingPopulationTradeArea[] | null;
  population: FloatingPopulationPopulation;
  benchmark: FloatingPopulationBenchmark;
  type: FloatingPopulationType;
  reliability: FloatingPopulationReliability;
  sources: FloatingPopulationSource[];
  trend: FloatingPopulationTrend | null;
  radius_profile: FloatingPopulationRadiusProfile | null;
  selection: FloatingPopulationSelection;
}

export const mockReportData = {
  address: '강원도 춘천시 후평동 234-5',
  floor: '2층',
  area: '전용 26평',
  rent: '월세 120만원',
  analyzedDate: '2026.08.22',

  aiConclusion: {
    industry: '네일·뷰티',
    reason:
      '전면폭 7.4m와 양호한 급·배수 조건이 뷰티 서비스업에 최적입니다. 반경 500m 내 동일 업종 경쟁점이 1개에 불과해 시장 진입 여건이 우수하며, 주변 주거 인구 비율이 높아 고정 고객 확보 가능성이 높습니다.',
  },

  recommended: [
    {
      rank: 1,
      name: '네일·뷰티',
      score: 92,
      tags: ['공간 구조 적합', '급·배수 활용 가능', '경쟁 강도 낮음'],
    },
    {
      rank: 2,
      name: '무인점포',
      score: 87,
      tags: ['24시간 운영 가능', '관리 인력 최소화', '소규모 면적 효율'],
    },
    {
      rank: 3,
      name: '소형 스튜디오',
      score: 82,
      tags: ['독립 출입 적합', '주거 인구 수요', '방음 조건 양호'],
    },
    {
      rank: 4,
      name: '코인세탁실',
      score: 78,
      tags: ['무인 운영 가능', '설비 투자 회수 빠름', '24시간 이용 수요'],
    },
    {
      rank: 5,
      name: '반려동물 미용',
      score: 73,
      tags: ['소형 평수 적합', '1인 운영 가능', '주거 인구 수요 부합'],
    },
  ] as RecommendedIndustry[],

  notRecommended: [
    {
      rank: 1,
      name: '고깃집',
      score: 31,
      tags: ['환기시설 부족', '배기 덕트 필요', '설비 공사 비용'],
    },
    {
      rank: 2,
      name: '대형 카페',
      score: 38,
      tags: ['면적 부족', '전력 용량 한계', '주차 불가'],
    },
    {
      rank: 3,
      name: '베이커리',
      score: 44,
      tags: ['오븐 설비 공사', '전력 증설 필요', '환기 개선 필요'],
    },
    {
      rank: 4,
      name: '노래방',
      score: 27,
      tags: ['방음 공사 필수', '심야 소음 민원 우려', '초기 인테리어 비용 큼'],
    },
    {
      rank: 5,
      name: '헬스장',
      score: 24,
      tags: ['층고 부족', '전용 면적 협소', '장비 하중 보강 필요'],
    },
  ] as RecommendedIndustry[],

  footTraffic: {
    dailyAverage: 4820,
    hourly: [
      { hour: '00시', count: 50 },
      { hour: '02시', count: 52 },
      { hour: '04시', count: 65 },
      { hour: '06시', count: 110 },
      { hour: '08시', count: 420 },
      { hour: '10시', count: 780 },
      { hour: '12시', count: 1100 },
      { hour: '14시', count: 900 },
      { hour: '16시', count: 1050 },
      { hour: '18시', count: 1300 },
      { hour: '20시', count: 850 },
      { hour: '22시', count: 350 },
      { hour: '24시', count: 100 },
    ] as FootTrafficHourly[],
    peakLabel: '네일·뷰티 영업시간대 (10:00-20:00)',
    ageGroups: [
      { label: '10대', percent: 4 },
      { label: '20대', percent: 28 },
      { label: '30대', percent: 26 },
      { label: '40대', percent: 21 },
      { label: '50대', percent: 14 },
      { label: '60대+', percent: 7 },
    ] as AgeGroupData[],
    source:
      'SK Planet 인구이동데이터 2025 · 시간대는 요일 평균, 연령대는 최근 30일 기준',
  },

  competitors: [
    { industry: '네일·뷰티', count: 1, recommended: true },
    { industry: '소형 스튜디오', count: 2, recommended: true },
    { industry: '무인점포', count: 3, recommended: true },
    { industry: '베이커리', count: 6, recommended: false },
    { industry: '고깃집', count: 9, recommended: false },
    { industry: '대형 카페', count: 12, recommended: false },
  ] as CompetitorData[],
  competitorSource: '소상공인진흥공단 상권정보시스템 2025',

  openClose: [
    { quarter: '2025 Q1', opened: 8, closed: 4 },
    { quarter: '2025 Q2', opened: 9, closed: 5 },
    { quarter: '2025 Q3', opened: 7, closed: 6 },
    { quarter: '2025 Q4', opened: 8, closed: 3 },
  ] as OpenCloseQuarter[],
  averageCloseRate: 12.4,
  openCloseSource: '국세청 사업자현황통계 2024',

  // 추천 5 업종 중 "무인점포"는 여기서도 의도적으로 뺐다 — commercial_area의
  // RECOMMENDED_NAME_TO_MIDDLE_CODE와 같은 이유로, 공통 업종 코드 75종에도
  // "무인점포"에 정확히 대응하는 항목이 없다. 기본 렌더링(props 없이 이
  // 목업을 쓸 때)에서도 adaptBusinessLifecycle()의 "이름 매칭 실패" 경로가
  // 실제로 걸리는 걸 보여주려고 남겨뒀다.
  // "코인세탁실"은 판단 보류(score: null, confidence: 'none',
  // data_status: 'unsupported') 케이스를 기본 화면에서도 보여주려고
  // 일부러 넣어뒀다 — 실제 응답도 75개 중 19개가 이 상태다.
  businessLifecycle: {
    summary:
      '네일·뷰티·소형 스튜디오는 개업이 활발하고 최근 폐업률도 낮아 안정적이며, 고깃집·노래방·베이커리는 폐업이 빠르게 늘고 폐업률도 과거보다 상승해 위험 신호가 뚜렷합니다.',
    coverage: {
      target_industries: 75,
      scored_industries: 56,
      unscored_industries: 19,
    },
    scoring_method: {
      description:
        '최근 개폐업 데이터와 폐업률 변화 추세를 기반으로 분석 가능한 업종끼리 상대 비교한 Lifecycle Score',
      score_type: 'relative',
      weights: {
        recent_year_close_rate: 0.35,
        net_change_rate: 0.25,
        turnover_stability: 0.2,
        close_rate_trend: 0.2,
      },
      notes: [
        'lifecycle_score는 미래 생존확률이 아니다.',
        'lifecycle_score는 분석 가능한 업종끼리 상대 비교한 점수이다.',
        '최근 1년 폐업률은 낮을수록 긍정적으로 평가한다.',
        '전체 분석기간 순증감률은 높을수록 긍정적으로 평가한다.',
        '회전율은 낮을수록 안정적으로 평가한다.',
        'close_rate_trend가 음수이면 과거보다 최근 폐업률이 낮아진 것이다.',
        'close_rate_trend가 양수이면 과거보다 최근 폐업률이 높아진 것이다.',
      ],
    },
    industries: [
      {
        industry_id: 'S209',
        industry_name: '네일·뷰티',
        score: 78.4,
        type: '성장·안정형',
        confidence: 'high',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 27,
          avg_store_count: 25.4,
          period_open_count: 20,
          period_close_count: 9,
          period_net_change: 11,
          avg_open_rate: 26.2,
          avg_close_rate: 11.8,
          net_change_rate: 14.4,
          turnover_rate: 38.0,
          recent_year_open_count: 7,
          recent_year_close_count: 2,
          recent_year_net_change: 5,
          recent_year_close_rate: 7.4,
          recent_year_net_change_rate: 18.5,
          oldest_year_close_rate: 15.8,
          close_rate_trend: -8.4,
        },
        evidence: [
          '최근 3년 동안 개업 20건, 폐업 9건으로 순증감은 +11건입니다.',
          '최근 1년 폐업률은 7.4%로, 3년 전 15.8%보다 낮아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 38.0%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'N102',
        industry_name: '소형 스튜디오',
        score: 66.7,
        type: '성장·안정형',
        confidence: 'medium',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 10,
          latest_store_count: 14,
          avg_store_count: 12.6,
          period_open_count: 9,
          period_close_count: 4,
          period_net_change: 5,
          avg_open_rate: 23.8,
          avg_close_rate: 10.6,
          net_change_rate: 13.2,
          turnover_rate: 34.4,
          recent_year_open_count: 4,
          recent_year_close_count: 1,
          recent_year_net_change: 3,
          recent_year_close_rate: 7.9,
          recent_year_net_change_rate: 23.6,
          oldest_year_close_rate: 13.2,
          close_rate_trend: -5.3,
        },
        evidence: [
          '최근 3년 동안 개업 9건, 폐업 4건으로 순증감은 +5건입니다.',
          '최근 1년 폐업률은 7.9%로, 3년 전 13.2%보다 낮아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 34.4%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'S208',
        industry_name: '코인세탁실',
        score: null,
        type: '판단 보류',
        confidence: 'none',
        data_available: false,
        score_available: false,
        data_status: 'unsupported',
        data_complete: false,
        metrics: {
          latest_store_count: null,
          avg_store_count: null,
          period_open_count: null,
          period_close_count: null,
          period_net_change: null,
          avg_open_rate: null,
          avg_close_rate: null,
          recent_year_close_rate: null,
          net_change_rate: null,
          turnover_rate: null,
          close_rate_trend: null,
        },
        source_coverage: {
          expected_source_count: 0,
          observed_source_rows: 0,
          expected_source_rows: 0,
          observed_quarters: 0,
        },
        evidence: [],
        warning: '서울시 생활밀접업종 데이터에 직접 대응 업종 없음',
      },
      {
        industry_id: 'S203',
        industry_name: '반려동물 미용',
        score: 58.9,
        type: '안정 유지형',
        confidence: 'medium',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 6,
          avg_store_count: 6.2,
          period_open_count: 3,
          period_close_count: 3,
          period_net_change: 0,
          avg_open_rate: 16.1,
          avg_close_rate: 16.1,
          net_change_rate: 0.0,
          turnover_rate: 32.2,
          recent_year_open_count: 1,
          recent_year_close_count: 1,
          recent_year_net_change: 0,
          recent_year_close_rate: 16.7,
          recent_year_net_change_rate: 0.0,
          oldest_year_close_rate: 16.7,
          close_rate_trend: 0.0,
        },
        evidence: [
          '최근 3년 동안 개업 3건, 폐업 3건으로 순증감은 0건입니다.',
          '최근 1년 폐업률은 16.7%로, 3년 전과 같은 수준입니다.',
          '개업률과 폐업률을 합한 회전율은 32.2%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'I201',
        industry_name: '고깃집',
        score: 32.5,
        type: '쇠퇴·위험형',
        confidence: 'high',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 32,
          avg_store_count: 34.1,
          period_open_count: 18,
          period_close_count: 29,
          period_net_change: -11,
          avg_open_rate: 17.6,
          avg_close_rate: 28.4,
          net_change_rate: -10.8,
          turnover_rate: 46.0,
          recent_year_open_count: 4,
          recent_year_close_count: 9,
          recent_year_net_change: -5,
          recent_year_close_rate: 26.4,
          recent_year_net_change_rate: -14.7,
          oldest_year_close_rate: 18.0,
          close_rate_trend: 8.4,
        },
        evidence: [
          '최근 3년 동안 개업 18건, 폐업 29건으로 순증감은 -11건입니다.',
          '최근 1년 폐업률은 26.4%로, 3년 전 18.0%보다 높아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 46.0%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'I212',
        industry_name: '대형 카페',
        score: 38.8,
        type: '과열·회전형',
        confidence: 'high',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 27,
          avg_store_count: 25.0,
          period_open_count: 22,
          period_close_count: 25,
          period_net_change: -3,
          avg_open_rate: 35.2,
          avg_close_rate: 40.0,
          net_change_rate: -4.8,
          turnover_rate: 75.2,
          recent_year_open_count: 8,
          recent_year_close_count: 9,
          recent_year_net_change: -1,
          recent_year_close_rate: 33.3,
          recent_year_net_change_rate: -3.7,
          oldest_year_close_rate: 25.0,
          close_rate_trend: 8.3,
        },
        evidence: [
          '최근 3년 동안 개업 22건, 폐업 25건으로 순증감은 -3건입니다.',
          '최근 1년 폐업률은 33.3%로, 3년 전 25.0%보다 높아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 75.2%로 업종 교체가 빈번합니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'I211',
        industry_name: '베이커리',
        score: 44.3,
        type: '쇠퇴·위험형',
        confidence: 'medium',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 16,
          avg_store_count: 17.4,
          period_open_count: 9,
          period_close_count: 15,
          period_net_change: -6,
          avg_open_rate: 20.7,
          avg_close_rate: 34.5,
          net_change_rate: -13.8,
          turnover_rate: 55.2,
          recent_year_open_count: 2,
          recent_year_close_count: 5,
          recent_year_net_change: -3,
          recent_year_close_rate: 31.3,
          recent_year_net_change_rate: -18.8,
          oldest_year_close_rate: 20.0,
          close_rate_trend: 11.3,
        },
        evidence: [
          '최근 3년 동안 개업 9건, 폐업 15건으로 순증감은 -6건입니다.',
          '최근 1년 폐업률은 31.3%로, 3년 전 20.0%보다 높아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 55.2%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'R208',
        industry_name: '노래방',
        score: 24.6,
        type: '쇠퇴·위험형',
        confidence: 'medium',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 10,
          avg_store_count: 12.9,
          period_open_count: 4,
          period_close_count: 15,
          period_net_change: -11,
          avg_open_rate: 10.3,
          avg_close_rate: 38.8,
          net_change_rate: -28.5,
          turnover_rate: 49.1,
          recent_year_open_count: 1,
          recent_year_close_count: 6,
          recent_year_net_change: -5,
          recent_year_close_rate: 46.5,
          recent_year_net_change_rate: -38.8,
          oldest_year_close_rate: 30.0,
          close_rate_trend: 16.5,
        },
        evidence: [
          '최근 3년 동안 개업 4건, 폐업 15건으로 순증감은 -11건입니다.',
          '최근 1년 폐업률은 46.5%로, 3년 전 30.0%보다 높아졌습니다.',
          '개업률과 폐업률을 합한 회전율은 49.1%입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'R206',
        industry_name: '헬스장',
        score: 41.2,
        type: '쇠퇴·위험형',
        confidence: 'low',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 9,
          latest_store_count: 4,
          avg_store_count: 4.6,
          period_open_count: 5,
          period_close_count: 6,
          period_net_change: -1,
          avg_open_rate: 39.3,
          avg_close_rate: 47.2,
          net_change_rate: -7.9,
          turnover_rate: 86.5,
          recent_year_open_count: 2,
          recent_year_close_count: 3,
          recent_year_net_change: -1,
          recent_year_close_rate: 65.2,
          recent_year_net_change_rate: -21.7,
          oldest_year_close_rate: 43.5,
          close_rate_trend: 21.7,
        },
        evidence: [
          '최근 9개 분기 동안 개업 5건, 폐업 6건으로 순증감은 -1건입니다.',
          '최근 1년 폐업률은 65.2%로, 과거 43.5%보다 높아졌습니다.',
        ],
        warning: '점포 수가 적어 분기별 개폐업 수치의 변동성이 클 수 있습니다.',
      },
    ],
  } as BusinessLifecycleData,

  // status를 'partial'로 둔 건 실제 백엔드 샘플(backend/examples/commercial_area/response.json)에서도
  // status가 'ok'인데 top-level warnings에 프랜차이즈 판정 caveat가 함께 내려오는 걸 확인했기 때문에,
  // 화면에서 "status가 partial이면 warnings를 각주로" 분기가 실제로 그려지는 모습을 확인할 수 있도록
  // 목업에서는 partial로 설정했다. no_data/error 분기는 CompetitorAnalysisSection.tsx의
  // getSectionVisibility()에 대한 별도 단위 검증으로 확인했다(스크린샷 대상 아님).
  commercialArea: {
    status: 'partial',
    warnings: [
      '프랜차이즈 업종 판정은 상호명을 공정거래위원회 가맹점 명단과 문자열로 대조한 결과라 누락·오탐이 있을 수 있습니다.',
    ],
    radiusM: 500,
    storeTotal: 342,
    dataReferenceDate: '2026.08.22 조회',

    byMajor: [
      {
        code: 'I2',
        name: '음식',
        count: 98,
        share: 0.2865,
        densityPerKm2: 124.8,
      },
      {
        code: 'G2',
        name: '소매',
        count: 71,
        share: 0.2076,
        densityPerKm2: 90.4,
      },
      {
        code: 'S2',
        name: '수리·개인',
        count: 54,
        share: 0.1579,
        densityPerKm2: 68.8,
      },
      {
        code: 'P1',
        name: '교육',
        count: 38,
        share: 0.1111,
        densityPerKm2: 48.4,
      },
      {
        code: 'Q1',
        name: '보건의료',
        count: 24,
        share: 0.0702,
        densityPerKm2: 30.6,
      },
      {
        code: 'L1',
        name: '부동산',
        count: 21,
        share: 0.0614,
        densityPerKm2: 26.7,
      },
      {
        code: 'M1',
        name: '과학·기술',
        count: 15,
        share: 0.0439,
        densityPerKm2: 19.1,
      },
      {
        code: 'R1',
        name: '예술·스포츠',
        count: 12,
        share: 0.0351,
        densityPerKm2: 15.3,
      },
      {
        code: 'N1',
        name: '시설관리·임대',
        count: 9,
        share: 0.0263,
        densityPerKm2: 11.5,
      },
    ] as CommercialAreaMajorCategory[],

    byRadius: [
      {
        radiusM: 50,
        storeTotal: 9,
        categoryCount: 7,
        absentCategoryCount: 68,
        topByCount: [],
      },
      {
        radiusM: 100,
        storeTotal: 22,
        categoryCount: 12,
        absentCategoryCount: 63,
        topByCount: [],
      },
      {
        radiusM: 200,
        storeTotal: 58,
        categoryCount: 21,
        absentCategoryCount: 54,
        topByCount: [],
      },
      {
        radiusM: 300,
        storeTotal: 118,
        categoryCount: 29,
        absentCategoryCount: 46,
        topByCount: [],
      },
      {
        radiusM: 500,
        storeTotal: 342,
        categoryCount: 41,
        absentCategoryCount: 34,
        topByCount: [
          {
            rank: 1,
            code: 'S207',
            name: '이용 및 미용업',
            count: 34,
            densityPerKm2: 43.3,
            note: '34개 · 이 반경 점포의 9.9%',
          },
          {
            rank: 2,
            code: 'I201',
            name: '한식 음식점업',
            count: 31,
            densityPerKm2: 39.5,
            note: '31개 · 이 반경 점포의 9.1%',
          },
          {
            rank: 3,
            code: 'I210',
            name: '기타 간이 음식점업',
            count: 28,
            densityPerKm2: 35.7,
            note: '28개 · 이 반경 점포의 8.2%',
          },
          {
            rank: 4,
            code: 'L102',
            name: '부동산 중개 및 대리업',
            count: 22,
            densityPerKm2: 28.0,
            note: '22개 · 이 반경 점포의 6.4%',
          },
          {
            rank: 5,
            code: 'Q102',
            name: '의원',
            count: 19,
            densityPerKm2: 24.2,
            note: '19개 · 이 반경 점포의 5.6%',
          },
          {
            rank: 6,
            code: 'G205',
            name: '체인화 편의점',
            count: 17,
            densityPerKm2: 21.6,
            note: '17개 · 이 반경 점포의 5.0%',
          },
          {
            rank: 7,
            code: 'I212',
            name: '비알코올 음료점업',
            count: 15,
            densityPerKm2: 19.1,
            note: '15개 · 이 반경 점포의 4.4%',
          },
          {
            rank: 8,
            code: 'S208',
            name: '세탁업',
            count: 12,
            densityPerKm2: 15.3,
            note: '12개 · 이 반경 점포의 3.5%',
          },
          {
            rank: 9,
            code: 'P106',
            name: '기타 교육기관',
            count: 11,
            densityPerKm2: 14.0,
            note: '11개 · 이 반경 점포의 3.2%',
          },
          {
            rank: 10,
            code: 'S203',
            name: '반려동물 관련 서비스업',
            count: 9,
            densityPerKm2: 11.5,
            note: '9개 · 이 반경 점포의 2.6%',
          },
        ],
      },
    ] as CommercialAreaRadiusSlice[],

    diversity: { effectiveCategories: 9.8 } as CommercialAreaDiversity,

    franchise: {
      count: 41,
      ratio: 0.1199,
      confidence: 'low',
    } as CommercialAreaFranchise,

    lqBaseline: {
      requestedRadiusM: 2000,
      appliedRadiusM: 2000,
    } as CommercialAreaLqBaseline,

    districtBaseline: {
      signguName: '춘천시',
    } as CommercialAreaDistrictBaseline,

    districtSpecialization: [
      {
        rank: 1,
        code: 'S207',
        name: '이용 및 미용업',
        count: 34,
        timesVsSurroundings: 2.8,
        note: '춘천시 전체보다 2.8배 많습니다',
      },
      {
        rank: 2,
        code: 'S203',
        name: '반려동물 관련 서비스업',
        count: 9,
        timesVsSurroundings: 2.4,
        note: '춘천시 전체보다 2.4배 많습니다',
      },
      {
        rank: 3,
        code: 'I201',
        name: '한식 음식점업',
        count: 31,
        timesVsSurroundings: 1.9,
        note: '춘천시 전체보다 1.9배 많습니다',
      },
      {
        rank: 4,
        code: 'I212',
        name: '비알코올 음료점업',
        count: 15,
        timesVsSurroundings: 1.7,
        note: '춘천시 전체보다 1.7배 많습니다',
      },
      {
        rank: 5,
        code: 'S208',
        name: '세탁업',
        count: 12,
        timesVsSurroundings: 1.6,
        note: '춘천시 전체보다 1.6배 많습니다',
      },
      {
        rank: 6,
        code: 'Q102',
        name: '의원',
        count: 19,
        timesVsSurroundings: 1.5,
        note: '춘천시 전체보다 1.5배 많습니다',
      },
      {
        rank: 7,
        code: 'P106',
        name: '기타 교육기관',
        count: 11,
        timesVsSurroundings: 1.4,
        note: '춘천시 전체보다 1.4배 많습니다',
      },
      {
        rank: 8,
        code: 'G205',
        name: '체인화 편의점',
        count: 17,
        timesVsSurroundings: 1.3,
        note: '춘천시 전체보다 1.3배 많습니다',
      },
      {
        rank: 9,
        code: 'I210',
        name: '기타 간이 음식점업',
        count: 28,
        timesVsSurroundings: 1.2,
        note: '춘천시 전체보다 1.2배 많습니다',
      },
      {
        rank: 10,
        code: 'L102',
        name: '부동산 중개 및 대리업',
        count: 22,
        timesVsSurroundings: 1.1,
        note: '춘천시 전체보다 1.1배 많습니다',
      },
    ] as CommercialAreaSpecializationRank[],

    // 추천 5 + 비추천 5 중 9개만 있다(무인점포는 의도적으로 뺐다 — 상권 데이터의
    // 표준 업종 분류 체계에는 '무인점포'라는 항목이 따로 없어 실제로도 매칭이
    // 자주 실패하는 사례를 재현한 것). RECOMMENDED_NAME_TO_MIDDLE_CODE에도
    // 무인점포 항목은 없다.
    byMiddleForRecommendations: [
      {
        code: 'S209',
        name: '네일미용업',
        sameTypeCount: 1,
        diffTypeCount: 341,
        lq: 0.82,
        lqDistrict: 0.91,
      },
      {
        code: 'N102',
        name: '사진 촬영 및 처리업',
        sameTypeCount: 2,
        diffTypeCount: 340,
        lq: 1.35,
        lqDistrict: 1.22,
      },
      {
        code: 'S208',
        name: '세탁업',
        sameTypeCount: 3,
        diffTypeCount: 339,
        lq: 0.65,
        lqDistrict: 0.58,
      },
      {
        code: 'S203',
        name: '반려동물 관련 서비스업',
        sameTypeCount: 2,
        diffTypeCount: 340,
        // 반경 2,000m 안에는 반려동물 서비스업 표본이 아예 없어 기준 자체가 없다(비교 불가).
        // 자치구 단위는 표본이 있어 lqDistrict는 정상 계산된다.
        lq: null,
        lqDistrict: 1.44,
      },
      {
        code: 'I201',
        name: '한식 음식점업',
        sameTypeCount: 9,
        diffTypeCount: 333,
        lq: 1.18,
        lqDistrict: 1.05,
      },
      {
        code: 'I212',
        name: '비알코올 음료점업',
        sameTypeCount: 12,
        diffTypeCount: 330,
        lq: 1.62,
        lqDistrict: 1.71,
      },
      {
        code: 'I211',
        name: '제과점업',
        sameTypeCount: 6,
        diffTypeCount: 336,
        lq: 0.94,
        lqDistrict: 0.88,
      },
      {
        code: 'R208',
        name: '노래연습장 운영업',
        sameTypeCount: 0,
        diffTypeCount: 342,
        // 이 반경엔 노래방이 0개라 배수가 실제로 0.0 — null(비교 불가)과 다르다.
        lq: 0.0,
        lqDistrict: 0.0,
      },
      {
        code: 'R206',
        name: '체력단련시설 운영업',
        sameTypeCount: 1,
        diffTypeCount: 341,
        lq: 0.31,
        lqDistrict: 0.27,
      },
    ] as CommercialAreaMiddleCategory[],
  } as CommercialAreaData,

  // status를 'partial'로 둔 이유는 commercialArea와 동일 — 화면에서
  // "status가 partial이면 warnings를 각주로" 분기가 실제로 그려지는지
  // 확인할 수 있게 한다. trend/radius_profile/trade_areas가 null인 케이스는
  // 별도로 floatingPopulationNullScenario(이 파일 하단)에서 확인한다.
  floatingPopulation: {
    status: 'partial',
    warnings: [
      '유동인구 유형은 직업 데이터가 아닌 연령·요일 분포에서 추정한 값입니다.',
      '상권영역 API가 폴리곤을 주지 않아 상권 구역을 면적 등가원으로 근사했습니다.',
    ],
    radius_m: 500,

    trade_areas: [
      { name: '후평동먹자골목', kind: '골목상권' },
      { name: '후평시장', kind: '전통시장' },
      { name: '온의로상권', kind: '발달상권' },
      { name: '후평2동행정복지센터앞', kind: '골목상권' },
      { name: '강원대학교후문', kind: '골목상권' },
      { name: '후평공단입구', kind: '골목상권' },
    ] as FloatingPopulationTradeArea[],

    population: {
      daily_avg: 4820,
      female_ratio: 0.52,
      age_share: {
        '10': 0.05,
        '20': 0.15,
        '30': 0.17,
        '40': 0.24,
        '50': 0.22,
        '60': 0.17,
      },
      time_per_hour_share: {
        '00_06': 0.06,
        '06_11': 0.13,
        '11_14': 0.19,
        '14_17': 0.17,
        '17_21': 0.28,
        '21_24': 0.17,
      },
      peak_time_band: '17_21',
      weekend_to_weekday_ratio: 1.12,
    } as FloatingPopulationPopulation,

    benchmark: {
      age_index: {
        '10': 0.85,
        '20': 0.62,
        '30': 0.71,
        '40': 1.18,
        '50': 1.55,
        '60': 1.42,
      },
      lunch_index: 0.92,
      evening_index: 1.35,
      night_index: 1.15,
      weekend_index: 1.18,
      scale_percentile: 58,
    } as FloatingPopulationBenchmark,

    type: {
      label: '주거생활형',
      reasons: [
        '40·50대 합이 46%로 이 지역 인구 구성에서 가장 큰 비중을 차지합니다.',
        '저녁 시간대(17~21시) 통행이 서울 평균의 1.35배로 많아 퇴근·귀가 동선에 몰려 있습니다.',
        '주말 통행량이 평일의 1.12배로 주말에 더 붐빕니다.',
      ],
      is_inference: true,
    } as FloatingPopulationType,

    reliability: {
      trade_area_count: 6,
      covered_trade_areas: 6,
      level: 'high',
    } as FloatingPopulationReliability,

    sources: [
      {
        name: '소상공인시장진흥공단 상권정보(유동인구)',
        license: '공공누리 1유형(출처표시)',
        period: '2026년 2분기',
      },
      {
        name: '통계청 생활인구 통계',
        license: '공공누리 1유형(출처표시)',
        period: '2026년 2분기',
      },
    ] as FloatingPopulationSource[],

    trend: {
      quarters: [
        { period: '2025년 3분기', daily_avg: 4460 },
        { period: '2025년 4분기', daily_avg: 4610 },
        { period: '2026년 1분기', daily_avg: 5050 },
        { period: '2026년 2분기', daily_avg: 4820 },
      ],
      direction: '보합',
      qoq_change: -4.6,
    } as FloatingPopulationTrend,

    radius_profile: {
      points: [
        { radius_m: 50, daily_avg: 210 },
        { radius_m: 100, daily_avg: 780 },
        { radius_m: 200, daily_avg: 1950 },
        { radius_m: 300, daily_avg: 3120 },
        { radius_m: 500, daily_avg: 4820 },
      ],
      method:
        '반경 안과 겹치는 상권의 길단위인구를 면적 비례로 안분해 추정했습니다.',
    } as FloatingPopulationRadiusProfile,

    selection: {
      applied: false,
      dropped: [],
      reason: null,
    } as FloatingPopulationSelection,
  } as FloatingPopulationData,

  aiSummary:
    '해당 공간은 대규모 조리시설이 필요하지 않은 소규모 서비스·리테일 업종에 높은 적합도를 보입니다. 특히 네일·뷰티, 무인점포, 소형 스튜디오가 공간 및 상권 조건과 가장 잘 부합합니다. 현재 공실 기간(4개월)을 고려할 때 초기 설비 비용이 적은 무인점포 또는 뷰티 업종을 우선 검토하는 것을 권장합니다.',

  aiAnalysisSummary: {
    exclusionReason:
      '고깃집·헬스장·노래방은 환기 덕트, 층고, 방음 등 별도 설비 공사가 필요한 업종입니다. 이 공간은 전용 26평의 2층 상가로 급·배수 확장이나 층고 보강에 제약이 있어 초기 공사 비용이 크게 늘어날 가능성이 높습니다. 대형 카페 역시 전력 용량과 좌석 면적이 부족해 동일한 이유로 우선순위에서 제외했습니다.',
    recommendationReason:
      '네일·뷰티는 반경 500m 내 동일 업종 경쟁점이 1개에 불과하고, 전면폭 7.4m와 기존 급·배수 조건을 그대로 활용할 수 있어 별도 설비 공사 없이 바로 입점이 가능합니다. 유동인구 데이터상 20·30대 여성 비중이 높은 시간대(10:00–20:00)와 영업시간이 겹치는 점도 긍정적입니다.',
    favorableConditions:
      '보증금과 월세가 낮은 소규모 공실일수록 초기 설비 투자가 적은 업종(무인점포, 코인세탁실)의 회수 기간이 짧아집니다. 반대로 주거 인구 비율이 높고 반복 방문 수요가 꾸준한 상권에서는 네일·뷰티, 반려동물 미용처럼 고정 고객 기반이 중요한 서비스업이 특히 유리합니다.',
    synergyTips:
      '네일·뷰티 매장을 주력으로 하되 한쪽 공간에 무인 결제형 스낵·음료 코너를 함께 두면 대기 고객의 체류 시간을 수익으로 전환할 수 있습니다. 영업시간 외 새벽·심야에는 코인세탁실처럼 무인으로 운영되는 업종과 공간을 나눠 쓰는 방식도 고정비 분산에 효과적입니다.',
  },
};

/**
 * 결정 에이전트가 쓰는 업종명(RecommendedIndustry.name)과 상권 에이전트의
 * 중분류 코드(CommercialAreaMiddleCategory.code)는 서로 다른 체계라 이름이
 * 문자 그대로 같지 않다. 실제 연동 전까지는 이 표로 수동 매핑하고, 표에
 * 없거나 byMiddleForRecommendations에서 해당 code를 못 찾으면 "매칭 안 됨"
 * 처리한다(무인점포가 의도적으로 빠져 있는 이유는 위 commercialArea 주석 참고).
 */
export const RECOMMENDED_NAME_TO_MIDDLE_CODE: Record<string, string> = {
  '네일·뷰티': 'S209',
  '소형 스튜디오': 'N102',
  코인세탁실: 'S208',
  '반려동물 미용': 'S203',
  고깃집: 'I201',
  '대형 카페': 'I212',
  베이커리: 'I211',
  노래방: 'R208',
  헬스장: 'R206',
};

/**
 * trend / radius_profile / trade_areas가 모두 null인 검증용 시나리오.
 * 상권 자료가 부실한 지역(예: 집계 상권이 1곳뿐이라 시계열·반경별 세부
 * 분석을 만들 수 없는 경우)을 흉내낸다. FloatingPopulationSection이
 * 이 세 섹션을 깔끔하게 숨기는지, selection.reason 문구가 대신 그 자리를
 * 설명하는지 확인하는 용도로만 쓴다(기본 화면에는 쓰이지 않는다).
 */
export const floatingPopulationNullScenario: FloatingPopulationData = {
  ...mockReportData.floatingPopulation,
  trade_areas: null,
  trend: null,
  radius_profile: null,
  selection: {
    applied: true,
    dropped: ['trend', 'radius_profile', 'trade_areas'],
    reason:
      '이 지역은 과거 분기 시계열과 반경별 세부 집계를 제공하는 상권이 없어 해당 분석을 생략했습니다.',
  },
};
