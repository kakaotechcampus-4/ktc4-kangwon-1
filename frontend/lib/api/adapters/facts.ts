import { INDUSTRIES, industryName } from '@/lib/api/industries';
import type { FactView, JsonValue } from '@/lib/api/types';

/**
 * GET /analyses/{id}/facts의 전체 fact를 리포트 차트 데이터로 바꾼다.
 * 지표 이름·단위는 backend/app/local_data와 agentic/scoring이 만드는 fact 기준이다.
 * 값이 없는(observed가 아닌) fact는 쓰지 않고, 필요한 fact가 하나도 없으면 null을
 * 돌려 화면이 "자료 없음"을 표시하게 한다.
 */

// ---------------------------------------------------------------------------
// 공통
// ---------------------------------------------------------------------------

function observed(facts: readonly FactView[], source: string, metric: string) {
  return facts.filter(
    (fact) =>
      fact.source === source &&
      fact.metric === metric &&
      fact.status === 'observed'
  );
}

/** 업종과 무관한 지역 전체 fact 하나 */
function areaFact(facts: readonly FactView[], source: string, metric: string) {
  return observed(facts, source, metric).find(
    (fact) => fact.industry_code === null
  );
}

/** 업종별 숫자 fact를 업종 코드 → 값으로 */
function byIndustry(
  facts: readonly FactView[],
  source: string,
  metric: string
): Map<string, number> {
  const values = new Map<string, number>();
  for (const fact of observed(facts, source, metric)) {
    if (fact.industry_code && typeof fact.value === 'number') {
      values.set(fact.industry_code, fact.value);
    }
  }
  return values;
}

function numberOf(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function numberMap(value: JsonValue | undefined): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, number] => typeof entry[1] === 'number'
    )
  );
}

/** "20262" → "2026년 2분기", "20252~20262" → "2025년 2분기~2026년 2분기" */
export function formatPeriod(period: string): string {
  return period.replace(/(\d{4})([1-4])(?!\d)/g, '$1년 $2분기');
}

function scopeNumber(fact: FactView | undefined, key: string): number | null {
  return numberOf(fact?.spatial_scope[key]);
}

// ---------------------------------------------------------------------------
// 유동인구
// ---------------------------------------------------------------------------

// by_time 구간과 길이(시간). 구간 길이가 달라 원값 대신 시간당 비중으로 비교한다.
const TIME_BANDS: { key: string; label: string; hours: number }[] = [
  { key: '00_06', label: '00~06시', hours: 6 },
  { key: '06_11', label: '06~11시', hours: 5 },
  { key: '11_14', label: '11~14시', hours: 3 },
  { key: '14_17', label: '14~17시', hours: 3 },
  { key: '17_21', label: '17~21시', hours: 4 },
  { key: '21_24', label: '21~24시', hours: 3 },
];

export interface FactShare {
  label: string;
  // 0~1
  share: number;
}

export interface FactFloatingPopulation {
  radiusM: number | null;
  period: string;
  tradeAreaCount: number | null;
  // 분석 상권 1곳의 하루 평균 유동인구(명)
  dailyPerTradeArea: number | null;
  // 시간당 유동인구 비중 — 막대끼리 비교할 수 있게 구간 길이로 나눈 뒤 합을 1로 맞춘다.
  timeBands: FactShare[];
  ageShares: FactShare[];
  // 주말/평일 비율을 서울 평균과 비교한 배수(1.0 = 서울 평균, 높을수록 주말형)
  weekendIndex: number | null;
  // 전년 같은 분기 대비 변화율(0.017 = +1.7%)
  yoyChange: number | null;
}

export function floatingPopulationFromFacts(
  facts: readonly FactView[]
): FactFloatingPopulation | null {
  const source = 'floating_population';
  const daily = areaFact(facts, source, 'mean_daily_per_trade_area');
  const byTime = areaFact(facts, source, 'by_time');
  const age = areaFact(facts, source, 'age_share');
  const weekend = areaFact(facts, source, 'weekend_index');
  const yoy = areaFact(facts, source, 'yoy_change');
  const anchor = daily ?? byTime ?? age;
  if (!anchor) {
    return null;
  }

  const times = numberMap(byTime?.value);
  const perHour = TIME_BANDS.filter((band) => band.key in times).map(
    (band) => ({ label: band.label, value: times[band.key] / band.hours })
  );
  const hourTotal = perHour.reduce((sum, band) => sum + band.value, 0);

  const ages = numberMap(age?.value);
  const ageTotal = Object.values(ages).reduce((sum, value) => sum + value, 0);
  const codes = anchor.spatial_scope.selected_trade_area_codes;

  return {
    radiusM: scopeNumber(anchor, 'radius_m'),
    period: formatPeriod(anchor.period),
    tradeAreaCount: Array.isArray(codes) ? codes.length : null,
    dailyPerTradeArea: numberOf(daily?.value),
    timeBands:
      hourTotal > 0
        ? perHour.map((band) => ({
            label: band.label,
            share: band.value / hourTotal,
          }))
        : [],
    ageShares:
      ageTotal > 0
        ? Object.keys(ages)
            .sort()
            .map((key) => ({
              label: key === '60' ? '60대 이상' : `${key}대`,
              share: ages[key] / ageTotal,
            }))
        : [],
    weekendIndex: numberOf(weekend?.value),
    yoyChange: numberOf(yoy?.value),
  };
}

// ---------------------------------------------------------------------------
// 경쟁 점포
// ---------------------------------------------------------------------------

export interface FactCompetitionRow {
  code: string;
  name: string;
  storeCount: number | null;
  densityPerKm2: number | null;
  // 유동인구 규모를 감안한 서울 대비 같은 업종 밀도(배수, 채점표 C1).
  // 1.0이면 서울 같은 업종 수준이고 높을수록 경쟁 부담이 크다.
  competitionIndex: number | null;
  // 비교 반경 대비 이 반경의 업종 비중(배수, 1보다 크면 이 주변에 더 몰려 있음)
  lq: number | null;
}

export interface FactCompetition {
  radiusM: number | null;
  comparisonRadiusM: number | null;
  period: string;
  // 51개 서비스 업종 점포 합계
  storeTotal: number;
  // 업종이 얼마나 고르게 섞여 있는지(유효 업종 수 = 1/HHI, 51개 업종 점포 수 기준)
  effectiveCategories: number | null;
  byMajor: { major: string; count: number }[];
  topByCount: FactCompetitionRow[];
  // 화면이 고른 업종(Top 5 등)만, 넘긴 순서대로
  selected: FactCompetitionRow[];
}

export function competitionFromFacts(
  facts: readonly FactView[],
  selectedCodes: readonly string[]
): FactCompetition | null {
  const source = 'commercial_area';
  const counts = byIndustry(facts, source, 'store_count');
  if (counts.size === 0) {
    return null;
  }
  const density = byIndustry(facts, source, 'density_per_km2');
  const competition = byIndustry(facts, source, 'competition_index');
  const lq = byIndustry(facts, source, 'lq');
  const anchor = observed(facts, source, 'store_count')[0];

  const row = (code: string): FactCompetitionRow => ({
    code,
    name: industryName(code),
    storeCount: counts.get(code) ?? null,
    densityPerKm2: density.get(code) ?? null,
    competitionIndex: competition.get(code) ?? null,
    lq: lq.get(code) ?? null,
  });

  const storeTotal = [...counts.values()].reduce(
    (sum, count) => sum + count,
    0
  );
  // 백엔드 differentiation은 업종마다 "자기 업종을 뺀" 값이라 지역 전체 지표로 쓰지 않는다.
  const hhi =
    storeTotal > 0
      ? [...counts.values()].reduce(
          (sum, count) => sum + (count / storeTotal) ** 2,
          0
        )
      : 0;

  const majors = new Map<string, number>();
  for (const [code, count] of counts) {
    const major = INDUSTRIES[code]?.major ?? '기타';
    majors.set(major, (majors.get(major) ?? 0) + count);
  }

  return {
    radiusM: scopeNumber(anchor, 'radius_m'),
    comparisonRadiusM: scopeNumber(anchor, 'comparison_radius_m'),
    period: formatPeriod(anchor.period),
    storeTotal,
    effectiveCategories: hhi > 0 ? 1 / hhi : null,
    byMajor: [...majors]
      .map(([major, count]) => ({ major, count }))
      .sort((a, b) => b.count - a.count),
    topByCount: [...counts.keys()]
      .map(row)
      .sort((a, b) => (b.storeCount ?? 0) - (a.storeCount ?? 0))
      .slice(0, 10),
    selected: selectedCodes.map(row),
  };
}

// ---------------------------------------------------------------------------
// 개폐업
// ---------------------------------------------------------------------------

export interface FactLifecycleRow {
  code: string;
  name: string;
  avgStoreCount: number | null;
  // 최근 1년 폐업률(%)
  recentCloseRate: number | null;
  // 서울 같은 업종 대비 폐업률(배수)
  closeRateRatio: number | null;
  // 개업·폐업이 함께 잦은 정도(%)
  turnoverRate: number | null;
  // 관측 기간 점포 순증감률(%)
  netChangeRate: number | null;
}

export interface FactLifecycle {
  period: string;
  rows: FactLifecycleRow[];
}

export function lifecycleFromFacts(
  facts: readonly FactView[],
  selectedCodes: readonly string[]
): FactLifecycle | null {
  const source = 'business_lifecycle';
  const recent = byIndustry(facts, source, 'recent_year_close_rate');
  if (recent.size === 0) {
    return null;
  }
  const average = byIndustry(facts, source, 'avg_store_count');
  const ratio = byIndustry(facts, source, 'close_rate_ratio');
  const turnover = byIndustry(facts, source, 'turnover_rate');
  const net = byIndustry(facts, source, 'net_change_rate');
  const anchor = observed(facts, source, 'recent_year_close_rate')[0];

  return {
    period: formatPeriod(anchor.period),
    rows: selectedCodes.map((code) => ({
      code,
      name: industryName(code),
      avgStoreCount: average.get(code) ?? null,
      recentCloseRate: recent.get(code) ?? null,
      closeRateRatio: ratio.get(code) ?? null,
      turnoverRate: turnover.get(code) ?? null,
      netChangeRate: net.get(code) ?? null,
    })),
  };
}
