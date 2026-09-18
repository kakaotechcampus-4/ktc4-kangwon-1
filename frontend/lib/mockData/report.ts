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

export type LifecycleConfidence = 'high' | 'medium' | 'low';

/**
 * 개폐업(business_lifecycle) 에이전트가 업종별로 내려주는 지표.
 * 백엔드 원본은 snake_case + metrics 중첩 구조이고, 이 파일의 다른 목업과
 * 표기를 맞추기 위해 camelCase로 평탄화했다. 실제 API 연동 시 매핑 기준:
 *   storeCount   ← industry_scores[].metrics.avg_store_count
 *   openCount    ← industry_scores[].metrics.annual_open_count
 *   closeCount   ← industry_scores[].metrics.annual_close_count
 *   netChange    ← industry_scores[].metrics.net_change
 *   closeRate    ← industry_scores[].metrics.avg_close_rate
 *   turnoverRate ← industry_scores[].metrics.turnover_rate
 *   score        ← industry_scores[].score  (= lifecycle_score)
 *   confidence   ← industry_scores[].confidence
 * 추천/비추천 구분은 이 에이전트가 내려주지 않으므로, 결정 에이전트 결과인
 * recommended / notRecommended 목록에서 업종명으로 파생한다.
 */
export type AgentStatus = 'ok' | 'partial' | 'no_data' | 'error';

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
 * 유동인구(floating_population) 에이전트 스키마
 * (backend/app/agents/floating_population/schemas.py, origin/feature/floating-population-agent
 * 브랜치, 커밋 3e30f74) 중 화면에 노출 가능한 필드만 옮겼다.
 *
 * 아래는 의도적으로 제외했다:
 *   - population.by_time, by_age, by_day: 분기 합계 원값. by_time은 구간
 *     길이가 3~6시간으로 달라 원값을 그대로 비교하면 "새벽에 사람이 가장
 *     많다"는 틀린 결론이 난다(반드시 time_per_hour_share만 쓴다). by_day는
 *     비중 필드가 없어 요일 차트 자체를 이번 구현에서 스킵했다(팀 결정 필요).
 *   - type.signals, thresholds, rules_version, is_inference: 판정 내부값,
 *     사용자 노출 금지.
 *   - data.period_code, unit, share_unit: 기계 판독용 문자열.
 *   - data.description: 결정 에이전트 LLM용 긴 설명문.
 *   - trade_areas의 code, distance_m, area_m2, equivalent_radius_m: 내부
 *     판정용. name/kind만 남겼다.
 *
 * ⚠️ trend / radiusProfile / selection 세 필드는 위 실제 스키마에 아직
 * 존재하지 않는다(FloatingPopulationData는 description/period_code/radius_m/
 * trade_areas/population/benchmark/type/reliability/sources 9개 필드뿐).
 * 이번 작업 지시에 필드명이 구체적으로 명시되어 있어 팀이 다음 단계로
 * 계획 중인 필드로 보고 우선 이 구조로 목업을 만들었다 — 실제 연동 시
 * 백엔드 담당과 필드명을 다시 확인해야 한다.
 */
export type ReliabilityLevel = 'high' | 'medium' | 'low';
export type TrendDirection = '증가' | '감소' | '보합';

export interface FloatingPopulationTradeArea {
  name: string;
  kind: string | null;
}

export interface FloatingPopulationPopulation {
  dailyAvg: number;
  femaleRatio: number;
  ageShare: Record<string, number>; // key: '10'|'20'|...|'60' ("60"은 60대+로 라벨링)
  timePerHourShare: Record<string, number>; // key: '00_06' 등, 반드시 이 필드만 사용
  peakTimeBand: string;
  weekendToWeekdayRatio: number;
}

export interface FloatingPopulationBenchmark {
  ageIndex: Record<string, number>; // 서울 평균 대비 배수(1.0 기준)
  lunchIndex: number;
  eveningIndex: number;
  nightIndex: number;
  weekendIndex: number;
  scalePercentile: number; // 서울 상권 중 규모 백분위
}

export interface FloatingPopulationType {
  label: string;
  reasons: string[];
}

export interface FloatingPopulationReliability {
  tradeAreaCount: number;
  coveredTradeAreas: number;
  level: ReliabilityLevel;
}

export interface FloatingPopulationSource {
  name: string;
  license: string;
  period: string;
}

export interface FloatingPopulationTrendQuarter {
  period: string;
  dailyAvg: number;
}

// ⚠️ 백엔드 미구현(위 설명 참고).
export interface FloatingPopulationTrend {
  quarters: FloatingPopulationTrendQuarter[];
  direction: TrendDirection;
  qoqChange: number; // % 단위. yoyChange는 항상 null이라 타입에서부터 뺐다(화면 비표시).
}

export interface FloatingPopulationRadiusPoint {
  radiusM: number;
  dailyAvg: number;
}

// ⚠️ 백엔드 미구현(위 설명 참고).
export interface FloatingPopulationRadiusProfile {
  points: FloatingPopulationRadiusPoint[];
  method: string;
}

// ⚠️ 백엔드 미구현(위 설명 참고).
export interface FloatingPopulationSelection {
  applied: boolean;
  dropped: string[]; // 예: ['trend', 'radius_profile'] — 어떤 하위 분석이 생략됐는지
  reason: string;
}

export interface FloatingPopulationData {
  status: AgentStatus;
  errorMessage?: string;
  warnings: string[];
  radiusM: number;
  tradeAreas: FloatingPopulationTradeArea[] | null;
  population: FloatingPopulationPopulation;
  benchmark: FloatingPopulationBenchmark;
  type: FloatingPopulationType;
  reliability: FloatingPopulationReliability;
  sources: FloatingPopulationSource[];
  trend: FloatingPopulationTrend | null;
  radiusProfile: FloatingPopulationRadiusProfile | null;
  selection: FloatingPopulationSelection;
}

export interface OpenCloseIndustryIndex {
  industryCode: string; // 실제 업종코드로 교체 예정(현재는 목업용 placeholder)
  industryName: string;
  storeCount: number;
  openCount: number;
  closeCount: number;
  netChange: number;
  closeRate: number;
  turnoverRate: number;
  score: number;
  confidence: LifecycleConfidence;
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

  // 추천 5 + 비추천 5, 총 10개 업종의 개폐업 지표.
  // confidence는 백엔드와 동일한 기준(점포수 20 이상 high / 5 이상 medium / 그 외 low)으로 맞췄다.
  openCloseIndex: [
    {
      industryCode: 'NB01',
      industryName: '네일·뷰티',
      storeCount: 24.5,
      openCount: 9,
      closeCount: 4,
      netChange: 5,
      closeRate: 8.2,
      turnoverRate: 26.5,
      score: 78.4,
      confidence: 'high',
    },
    {
      industryCode: 'UM01',
      industryName: '무인점포',
      storeCount: 18.2,
      openCount: 11,
      closeCount: 5,
      netChange: 6,
      closeRate: 9.6,
      turnoverRate: 31.2,
      score: 74.1,
      confidence: 'medium',
    },
    {
      industryCode: 'ST01',
      industryName: '소형 스튜디오',
      storeCount: 12.8,
      openCount: 6,
      closeCount: 4,
      netChange: 2,
      closeRate: 11.4,
      turnoverRate: 24.8,
      score: 66.7,
      confidence: 'medium',
    },
    {
      industryCode: 'CL01',
      industryName: '코인세탁실',
      storeCount: 8.4,
      openCount: 4,
      closeCount: 2,
      netChange: 2,
      closeRate: 7.1,
      turnoverRate: 19.3,
      score: 71.2,
      confidence: 'medium',
    },
    {
      industryCode: 'PG01',
      industryName: '반려동물 미용',
      storeCount: 6.2,
      openCount: 3,
      closeCount: 3,
      netChange: 0,
      closeRate: 12.8,
      turnoverRate: 22.6,
      score: 58.9,
      confidence: 'medium',
    },
    {
      industryCode: 'GJ01',
      industryName: '고깃집',
      storeCount: 31.6,
      openCount: 8,
      closeCount: 13,
      netChange: -5,
      closeRate: 19.4,
      turnoverRate: 38.7,
      score: 32.5,
      confidence: 'high',
    },
    {
      industryCode: 'CF01',
      industryName: '대형 카페',
      storeCount: 27.3,
      openCount: 10,
      closeCount: 12,
      netChange: -2,
      closeRate: 17.2,
      turnoverRate: 41.5,
      score: 38.8,
      confidence: 'high',
    },
    {
      industryCode: 'BK01',
      industryName: '베이커리',
      storeCount: 15.7,
      openCount: 5,
      closeCount: 7,
      netChange: -2,
      closeRate: 15.6,
      turnoverRate: 29.4,
      score: 44.3,
      confidence: 'medium',
    },
    {
      industryCode: 'KR01',
      industryName: '노래방',
      storeCount: 9.8,
      openCount: 2,
      closeCount: 6,
      netChange: -4,
      closeRate: 22.7,
      turnoverRate: 33.1,
      score: 24.6,
      confidence: 'medium',
    },
    {
      industryCode: 'GY01',
      industryName: '헬스장',
      storeCount: 4.3,
      openCount: 2,
      closeCount: 3,
      netChange: -1,
      closeRate: 16.9,
      turnoverRate: 27.8,
      score: 41.2,
      confidence: 'low',
    },
  ] as OpenCloseIndustryIndex[],

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
  // 확인할 수 있게 한다. trend/radiusProfile/tradeAreas가 null인 케이스는
  // 별도로 floatingPopulationNullScenario(이 파일 하단)에서 확인한다.
  floatingPopulation: {
    status: 'partial',
    warnings: [
      '유동인구 유형은 직업 데이터가 아닌 연령·요일 분포에서 추정한 값입니다.',
      '상권영역 API가 폴리곤을 주지 않아 상권 구역을 면적 등가원으로 근사했습니다.',
    ],
    radiusM: 500,

    tradeAreas: [
      { name: '후평동먹자골목', kind: '골목상권' },
      { name: '후평시장', kind: '전통시장' },
      { name: '온의로상권', kind: '발달상권' },
      { name: '후평2동행정복지센터앞', kind: '골목상권' },
      { name: '강원대학교후문', kind: '골목상권' },
      { name: '후평공단입구', kind: '골목상권' },
    ] as FloatingPopulationTradeArea[],

    population: {
      dailyAvg: 4820,
      femaleRatio: 0.52,
      ageShare: {
        '10': 0.05,
        '20': 0.15,
        '30': 0.17,
        '40': 0.24,
        '50': 0.22,
        '60': 0.17,
      },
      timePerHourShare: {
        '00_06': 0.06,
        '06_11': 0.13,
        '11_14': 0.19,
        '14_17': 0.17,
        '17_21': 0.28,
        '21_24': 0.17,
      },
      peakTimeBand: '17_21',
      weekendToWeekdayRatio: 1.12,
    } as FloatingPopulationPopulation,

    benchmark: {
      ageIndex: {
        '10': 0.85,
        '20': 0.62,
        '30': 0.71,
        '40': 1.18,
        '50': 1.55,
        '60': 1.42,
      },
      lunchIndex: 0.92,
      eveningIndex: 1.35,
      nightIndex: 1.15,
      weekendIndex: 1.18,
      scalePercentile: 58,
    } as FloatingPopulationBenchmark,

    type: {
      label: '주거생활형',
      reasons: [
        '40·50대 합이 46%로 이 지역 인구 구성에서 가장 큰 비중을 차지합니다.',
        '저녁 시간대(17~21시) 통행이 서울 평균의 1.35배로 많아 퇴근·귀가 동선에 몰려 있습니다.',
        '주말 통행량이 평일의 1.12배로 주말에 더 붐빕니다.',
      ],
    } as FloatingPopulationType,

    reliability: {
      tradeAreaCount: 6,
      coveredTradeAreas: 6,
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
        { period: '2025년 3분기', dailyAvg: 4460 },
        { period: '2025년 4분기', dailyAvg: 4610 },
        { period: '2026년 1분기', dailyAvg: 5050 },
        { period: '2026년 2분기', dailyAvg: 4820 },
      ],
      direction: '보합',
      qoqChange: -4.6,
    } as FloatingPopulationTrend,

    radiusProfile: {
      points: [
        { radiusM: 50, dailyAvg: 210 },
        { radiusM: 100, dailyAvg: 780 },
        { radiusM: 200, dailyAvg: 1950 },
        { radiusM: 300, dailyAvg: 3120 },
        { radiusM: 500, dailyAvg: 4820 },
      ],
      method:
        '반경 안과 겹치는 상권의 길단위인구를 면적 비례로 안분해 추정했습니다.',
    } as FloatingPopulationRadiusProfile,

    selection: {
      applied: false,
      dropped: [],
      reason: '',
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
 * trend / radiusProfile / tradeAreas가 모두 null인 검증용 시나리오.
 * 상권 자료가 부실한 지역(예: 집계 상권이 1곳뿐이라 시계열·반경별 세부
 * 분석을 만들 수 없는 경우)을 흉내낸다. FloatingPopulationSection이
 * 이 세 섹션을 깔끔하게 숨기는지, selection.reason 문구가 대신 그 자리를
 * 설명하는지 확인하는 용도로만 쓴다(기본 화면에는 쓰이지 않는다).
 */
export const floatingPopulationNullScenario: FloatingPopulationData = {
  ...mockReportData.floatingPopulation,
  tradeAreas: null,
  trend: null,
  radiusProfile: null,
  selection: {
    applied: true,
    dropped: ['trend', 'radius_profile', 'trade_areas'],
    reason:
      '이 지역은 과거 분기 시계열과 반경별 세부 집계를 제공하는 상권이 없어 해당 분석을 생략했습니다.',
  },
};
