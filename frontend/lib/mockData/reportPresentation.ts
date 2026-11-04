import { INDUSTRIES } from '@/lib/api/industries';
import {
  mockReportData,
  RECOMMENDED_NAME_TO_MIDDLE_CODE,
} from '@/lib/mockData/report';
import type {
  FactCompetition,
  FactCompetitionRow,
  FactFloatingPopulation,
  FactLifecycle,
} from '@/lib/api/adapters/facts';

/** 오금로 404 예시 리포트에서 실제 리포트와 같은 fact 기반 화면에 쓰는 샘플. */
export const mockFloatingPopulationFacts: FactFloatingPopulation = {
  radiusM: 500,
  period: '2026년 2분기',
  tradeAreaCount: 5,
  dailyPerTradeArea: 8688,
  // 저녁 퇴근·귀가 시간에 유동이 가장 많고, 심야 시간대가 가장 많다는
  // 이전 샘플의 서로 모순된 조합을 바로잡았다.
  timeBands: [
    { label: '00~06시', share: 0.105 },
    { label: '06~11시', share: 0.145 },
    { label: '11~14시', share: 0.17 },
    { label: '14~17시', share: 0.18 },
    { label: '17~21시', share: 0.225 },
    { label: '21~24시', share: 0.175 },
  ],
  ageShares: [
    { label: '10대', share: 0.09 },
    { label: '20대', share: 0.13 },
    { label: '30대', share: 0.19 },
    { label: '40대', share: 0.24 },
    { label: '50대', share: 0.21 },
    { label: '60대 이상', share: 0.14 },
  ],
  weekendIndex: 1.08,
  yoyChange: 0.03,
};

const row = (
  code: string,
  storeCount: number,
  densityPerKm2: number,
  competitionIndex: number,
  lq: number,
  densityKind: FactCompetitionRow['densityKind']
): FactCompetitionRow => ({
  code,
  name: INDUSTRIES[code].name,
  storeCount,
  densityPerKm2,
  competitionIndex,
  lq,
  densityKind,
});

/** 추천·제외 업종은 모두 서비스의 51개 정식 업종 코드에서만 고른다. */
export const mockRecommendedIndustryCodes = new Set([
  'I212', // 카페·비알코올 음료점
  'S207', // 이용·미용
  'P105', // 학원·교육기관
  'S209', // 세탁
  'G205', // 식료품 소매
]);

const recommendedRows: FactCompetitionRow[] = [
  row('I212', 34, 43.3, 0.78, 0.92, '근처형'),
  row('S207', 67, 85.3, 0.75, 1.23, '근처형'),
  row('P105', 56, 71.3, 1.12, 1.27, '모임형'),
  row('S209', 18, 22.9, 0.82, 0.88, '근처형'),
  row('G205', 42, 53.5, 0.91, 1.04, '근처형'),
];

const excludedRows: FactCompetitionRow[] = [
  row('I211', 29, 36.9, 1.42, 1.36, '모임형'),
  row('I201', 83, 105.7, 1.28, 1.18, '모임형'),
  row('I101', 7, 8.9, 1.31, 1.12, '무관'),
  row('G202', 4, 5.1, 0.48, 0.52, '무관'),
  row('N109', 3, 3.8, 0.55, 0.61, '무관'),
];

export const mockCompetitionFacts: FactCompetition = {
  radiusM: 500,
  comparisonRadiusM: 2000,
  period: '2026년 2분기',
  storeTotal: 795,
  effectiveCategories: 17.3,
  byMajor: [
    { major: '음식점업', count: 208 },
    { major: '소매업', count: 164 },
    { major: '수리 및 개인 서비스업', count: 120 },
    { major: '교육 서비스업', count: 113 },
    { major: '보건의료업', count: 82 },
    { major: '기타 업종', count: 108 },
  ],
  topByCount: [
    row('I201', 83, 105.7, 1.28, 1.18, '모임형'),
    row('S207', 67, 85.3, 0.75, 1.23, '근처형'),
    row('P105', 56, 71.3, 1.12, 1.27, '모임형'),
    row('G205', 42, 53.5, 0.91, 1.04, '근처형'),
    row('I212', 34, 43.3, 0.78, 0.92, '근처형'),
    row('Q102', 31, 39.5, 1.04, 1.03, '근처형'),
    row('I211', 29, 36.9, 1.42, 1.36, '모임형'),
    row('L102', 29, 36.9, 0.95, 0.98, '무관'),
    row('G215', 21, 26.7, 1.08, 1.02, '근처형'),
    row('S209', 18, 22.9, 0.82, 0.88, '근처형'),
  ],
  selected: [...recommendedRows, ...excludedRows],
};

const recommendedLifecycle: FactLifecycle['rows'] = [
  {
    code: 'I212',
    name: INDUSTRIES.I212.name,
    avgStoreCount: 32.4,
    recentCloseRate: 8.2,
    closeRateRatio: 0.91,
    turnoverRate: 18.6,
    netChangeRate: 4.8,
  },
  {
    code: 'S207',
    name: INDUSTRIES.S207.name,
    avgStoreCount: 64.1,
    recentCloseRate: 7.6,
    closeRateRatio: 0.86,
    turnoverRate: 16.2,
    netChangeRate: 5.2,
  },
  {
    code: 'P105',
    name: INDUSTRIES.P105.name,
    avgStoreCount: 51.7,
    recentCloseRate: 6.9,
    closeRateRatio: 0.82,
    turnoverRate: 13.4,
    netChangeRate: 6.1,
  },
  {
    code: 'S209',
    name: INDUSTRIES.S209.name,
    avgStoreCount: 17.3,
    recentCloseRate: 8.8,
    closeRateRatio: 0.96,
    turnoverRate: 17.5,
    netChangeRate: 2.7,
  },
  {
    code: 'G205',
    name: INDUSTRIES.G205.name,
    avgStoreCount: 39.8,
    recentCloseRate: 9.1,
    closeRateRatio: 0.99,
    turnoverRate: 19.3,
    netChangeRate: 1.8,
  },
];

const excludedLifecycle: FactLifecycle['rows'] = [
  {
    code: 'I211',
    name: INDUSTRIES.I211.name,
    avgStoreCount: 27.6,
    recentCloseRate: 13.4,
    closeRateRatio: 1.28,
    turnoverRate: 27.2,
    netChangeRate: -3.8,
  },
  {
    code: 'I201',
    name: INDUSTRIES.I201.name,
    avgStoreCount: 80.2,
    recentCloseRate: 11.8,
    closeRateRatio: 1.14,
    turnoverRate: 24.6,
    netChangeRate: -1.9,
  },
  {
    code: 'I101',
    name: INDUSTRIES.I101.name,
    avgStoreCount: 6.5,
    recentCloseRate: 12.6,
    closeRateRatio: 1.2,
    turnoverRate: 25.1,
    netChangeRate: -2.5,
  },
  {
    code: 'G202',
    name: INDUSTRIES.G202.name,
    avgStoreCount: 4.1,
    recentCloseRate: 10.4,
    closeRateRatio: 1.02,
    turnoverRate: 20.8,
    netChangeRate: -0.8,
  },
  {
    code: 'N109',
    name: INDUSTRIES.N109.name,
    avgStoreCount: 2.8,
    recentCloseRate: 11.3,
    closeRateRatio: 1.08,
    turnoverRate: 21.7,
    netChangeRate: -1.2,
  },
];

export const mockLifecycleFacts: FactLifecycle = {
  period: '2023년 3분기~2026년 2분기',
  rows: [...recommendedLifecycle, ...excludedLifecycle],
};

/** 핵심결론의 추천·제외 순서와 같은 기준으로 51개 검토 순위를 보여준다. */
const recommendedOrder = mockReportData.recommended
  .map((item) => RECOMMENDED_NAME_TO_MIDDLE_CODE[item.name])
  .filter((code): code is string => Boolean(code));
const excludedOrder = mockReportData.notRecommended
  .map((item) => RECOMMENDED_NAME_TO_MIDDLE_CODE[item.name])
  .filter((code): code is string => Boolean(code));
const otherCodes = Object.keys(INDUSTRIES).filter(
  (code) => !recommendedOrder.includes(code) && !excludedOrder.includes(code)
);
export const mockIndustryRankingCodes = [
  ...recommendedOrder,
  ...otherCodes,
  ...excludedOrder,
];
