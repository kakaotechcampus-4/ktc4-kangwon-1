import type {
  FactCompetition,
  FactCompetitionRow,
  FactFloatingPopulation,
  FactLifecycle,
} from '@/lib/api/adapters/facts';
import { mockReportData } from '@/lib/mockData/report';

/**
 * 예시 리포트에서 실제 분석 리포트와 같은 fact 기반 화면을 보여주기 위한
 * 고정 샘플. 실제 데이터 어댑터가 노출하는 필드만 포함해 목업 전용 표현이
 * 실제 화면과 달라지는 일을 막는다.
 */
export const mockFloatingPopulationFacts: FactFloatingPopulation = {
  radiusM: 500,
  period: '2026년 2분기',
  tradeAreaCount: 5,
  dailyPerTradeArea: 8688.1,
  timeBands: [
    { label: '00~06시', share: 0.1953 },
    { label: '06~11시', share: 0.1673 },
    { label: '11~14시', share: 0.1511 },
    { label: '14~17시', share: 0.1477 },
    { label: '17~21시', share: 0.1593 },
    { label: '21~24시', share: 0.1794 },
  ],
  ageShares: [
    { label: '10대', share: 0.1967 },
    { label: '20대', share: 0.101 },
    { label: '30대', share: 0.1379 },
    { label: '40대', share: 0.1537 },
    { label: '50대', share: 0.1567 },
    { label: '60대 이상', share: 0.254 },
  ],
  weekendIndex: 1.014,
  // 현재 fact 응답에 전년 동기 지표가 없으면 화면에서도 '자료 없음'을 보여준다.
  yoyChange: -0.06,
};

const competitionRows: FactCompetitionRow[] = [
  {
    code: 'S209',
    name: '네일·뷰티',
    storeCount: 1,
    densityPerKm2: 1.3,
    competitionIndex: 0.82,
    lq: 0.91,
    densityKind: '근처형',
  },
  // 예시 데이터에는 표준 업종 코드가 없어도 이름과 추천 상태는 표시한다.
  {
    code: 'MOCK_UNMAPPED',
    name: '무인점포',
    storeCount: 3,
    densityPerKm2: 3.8,
    competitionIndex: null,
    lq: null,
    densityKind: null,
  },
  {
    code: 'N102',
    name: '소형 스튜디오',
    storeCount: 2,
    densityPerKm2: 2.5,
    competitionIndex: 1.35,
    lq: 1.22,
    densityKind: '모임형',
  },
  {
    code: 'S208',
    name: '코인세탁실',
    storeCount: 3,
    densityPerKm2: 3.8,
    competitionIndex: 0.65,
    lq: 0.58,
    densityKind: '근처형',
  },
  {
    code: 'S203',
    name: '반려동물 미용',
    storeCount: 2,
    densityPerKm2: 2.5,
    competitionIndex: 1.12,
    lq: null,
    densityKind: '근처형',
  },
  {
    code: 'I201',
    name: '고깃집',
    storeCount: 9,
    densityPerKm2: 11.5,
    competitionIndex: 1.18,
    lq: 1.05,
    densityKind: '모임형',
  },
  {
    code: 'I212',
    name: '대형 카페',
    storeCount: 12,
    densityPerKm2: 15.3,
    competitionIndex: 1.62,
    lq: 1.71,
    densityKind: '근처형',
  },
  {
    code: 'I211',
    name: '베이커리',
    storeCount: 6,
    densityPerKm2: 7.6,
    competitionIndex: 1.08,
    lq: 1.15,
    densityKind: '모임형',
  },
  {
    code: 'R207',
    name: '필라테스',
    storeCount: null,
    densityPerKm2: null,
    competitionIndex: null,
    lq: null,
    densityKind: null,
  },
  {
    code: 'R206',
    name: '헬스장',
    storeCount: 4,
    densityPerKm2: 5.1,
    competitionIndex: 0.92,
    lq: 1.11,
    densityKind: '모임형',
  },
];

export const mockCompetitionFacts: FactCompetition = {
  radiusM: 500,
  comparisonRadiusM: 2000,
  period: '2026년 2분기',
  storeTotal: 795,
  effectiveCategories: 17.3,
  byMajor: [
    { major: '음식', count: 208 },
    { major: '소매', count: 164 },
    { major: '수리·개인 서비스', count: 120 },
    { major: '교육', count: 113 },
    { major: '보건·의료', count: 82 },
    { major: '기타', count: 108 },
  ],
  topByCount: [
    {
      code: 'S207',
      name: '이용·미용',
      storeCount: 67,
      densityPerKm2: 85.3,
      competitionIndex: 0.75,
      lq: 1.23,
      densityKind: '근처형',
    },
    {
      code: 'P106',
      name: '학원·교육기관',
      storeCount: 56,
      densityPerKm2: 71.3,
      competitionIndex: 1.62,
      lq: 1.27,
      densityKind: '모임형',
    },
    {
      code: 'Q102',
      name: '의약품·의료기기 소매',
      storeCount: 21,
      densityPerKm2: 26.7,
      competitionIndex: 1.08,
      lq: 1.71,
      densityKind: '근처형',
    },
    {
      code: 'G201',
      name: '종합 소매',
      storeCount: 21,
      densityPerKm2: 26.7,
      competitionIndex: 0.39,
      lq: 0.71,
      densityKind: '근처형',
    },
    {
      code: 'L102',
      name: '부동산 관련 서비스',
      storeCount: 29,
      densityPerKm2: 36.9,
      competitionIndex: 0.45,
      lq: 0.61,
      densityKind: '근처형',
    },
    {
      code: 'I212',
      name: '카페·비알코올 음료점',
      storeCount: 34,
      densityPerKm2: 43.3,
      competitionIndex: 0.6,
      lq: 0.92,
      densityKind: '근처형',
    },
    {
      code: 'G208',
      name: '가전·정보통신장비 소매',
      storeCount: 11,
      densityPerKm2: 14,
      competitionIndex: 0.92,
      lq: 1.11,
      densityKind: '모임형',
    },
    {
      code: 'G213',
      name: '문화·오락·여가용품 소매',
      storeCount: 8,
      densityPerKm2: 10.2,
      competitionIndex: 1,
      lq: 1.15,
      densityKind: '모임형',
    },
    {
      code: 'S207A',
      name: '화장품 소매',
      storeCount: 8,
      densityPerKm2: 10.2,
      competitionIndex: 0.73,
      lq: 1.01,
      densityKind: '모임형',
    },
    {
      code: 'G204',
      name: '의류·신발·가방·섬유 소매',
      storeCount: 24,
      densityPerKm2: 30.6,
      competitionIndex: 0.6,
      lq: 0.95,
      densityKind: '모임형',
    },
  ],
  selected: competitionRows,
};

export const mockRecommendedIndustryCodes = new Set(
  mockCompetitionFacts.selected.slice(0, 5).map((row) => row.code)
);

const lifecycleCodes: Record<string, string> = {
  '네일·뷰티': 'S209',
  '소형 스튜디오': 'N102',
  코인세탁실: 'S208',
  '반려동물 미용': 'S203',
  고깃집: 'I201',
  '대형 카페': 'I212',
  베이커리: 'I211',
  필라테스: 'R207',
  헬스장: 'R206',
};

const lifecycleCloseRateRatios: Record<string, number | null> = {
  '네일·뷰티': 0.82,
  '소형 스튜디오': 0.91,
  코인세탁실: null,
  '반려동물 미용': 1.04,
  고깃집: 1.28,
  '대형 카페': 1.42,
  베이커리: 1.31,
  필라테스: null,
  헬스장: 1.67,
};

export const mockLifecycleFacts: FactLifecycle = {
  period: '2023년 3분기~2026년 2분기',
  rows: [...mockReportData.recommended, ...mockReportData.notRecommended].map(
    (candidate) => {
      const source = mockReportData.businessLifecycle.industries.find(
        (item) => item.industry_id === lifecycleCodes[candidate.name]
      );
      const metrics = source?.metrics;
      return {
        code: lifecycleCodes[candidate.name] ?? candidate.name,
        name: candidate.name,
        avgStoreCount: metrics?.avg_store_count ?? null,
        recentCloseRate: metrics?.recent_year_close_rate ?? null,
        closeRateRatio: lifecycleCloseRateRatios[candidate.name] ?? null,
        turnoverRate: metrics?.turnover_rate ?? null,
        netChangeRate: metrics?.net_change_rate ?? null,
      };
    }
  ),
};
