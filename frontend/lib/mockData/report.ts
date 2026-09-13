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

  aiSummary:
    '해당 공간은 대규모 조리시설이 필요하지 않은 소규모 서비스·리테일 업종에 높은 적합도를 보입니다. 특히 네일·뷰티, 무인점포, 소형 스튜디오가 공간 및 상권 조건과 가장 잘 부합합니다. 현재 공실 기간(4개월)을 고려할 때 초기 설비 비용이 적은 무인점포 또는 뷰티 업종을 우선 검토하는 것을 권장합니다.',
};
