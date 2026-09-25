import type {
  AgentStatus,
  FloatingPopulationBenchmark,
  FloatingPopulationData,
  FloatingPopulationPopulation,
  FloatingPopulationRadiusPoint,
  FloatingPopulationRadiusProfile,
  FloatingPopulationReliability,
  FloatingPopulationSelection,
  FloatingPopulationSource,
  FloatingPopulationTradeArea,
  FloatingPopulationTrend,
  FloatingPopulationTrendQuarter,
  FloatingPopulationType,
  ReliabilityLevel,
  TrendDirection,
} from '@/lib/mockData/report';
import {
  asArray,
  asNullableNumber,
  asNumber,
  asRecord,
  asString,
} from './shared';

/**
 * floating_population 에이전트의 실제 출력
 * (backend/app/agents/floating_population/schemas.py의 FloatingPopulationData,
 * snake_case)을 화면이 쓰는 같은 이름의 타입(lib/mockData/report.ts)으로
 * 옮긴다. business_lifecycle과 같은 이유로 필드명을 camelCase로 바꾸지
 * 않는다(타입 파일 상단 주석 참고).
 *
 * status/warnings/errorMessage는 이 함수가 받는 raw(=AgentAnalysis.data)
 * 안에 없다 — commercialArea.ts와 동일하게 envelope 인자로 따로 받는다.
 */
type Envelope = {
  status: AgentStatus;
  warnings?: string[];
  errorMessage?: string;
};

function mapTradeArea(raw: unknown): FloatingPopulationTradeArea {
  const r = asRecord(raw);
  return {
    name: asString(r.name),
    kind: typeof r.kind === 'string' ? r.kind : null,
  };
}

function mapPopulation(raw: unknown): FloatingPopulationPopulation {
  const r = asRecord(raw);
  return {
    daily_avg: asNumber(r.daily_avg),
    female_ratio: asNumber(r.female_ratio),
    age_share: asNumberRecord(r.age_share),
    time_per_hour_share: asNumberRecord(r.time_per_hour_share),
    peak_time_band: asString(r.peak_time_band),
    weekend_to_weekday_ratio: asNumber(r.weekend_to_weekday_ratio),
  };
}

// age_share/age_index/time_per_hour_share는 키가 고정돼 있지 않은 값-객체다
// (예: '10'|'20'|...|'60') — shared.ts의 asRecord/asNumber를 조합해 값마다
// 안전하게 숫자로 옮긴다.
function asNumberRecord(raw: unknown): Record<string, number> {
  const r = asRecord(raw);
  const result: Record<string, number> = {};
  for (const key of Object.keys(r)) {
    result[key] = asNumber(r[key]);
  }
  return result;
}

function mapBenchmark(raw: unknown): FloatingPopulationBenchmark {
  const r = asRecord(raw);
  return {
    age_index: asNumberRecord(r.age_index),
    lunch_index: asNumber(r.lunch_index),
    evening_index: asNumber(r.evening_index),
    night_index: asNumber(r.night_index),
    weekend_index: asNumber(r.weekend_index),
    scale_percentile: asNumber(r.scale_percentile),
  };
}

function mapType(raw: unknown): FloatingPopulationType {
  const r = asRecord(raw);
  return {
    label: asString(r.label),
    reasons: asArray(r.reasons).filter(
      (v): v is string => typeof v === 'string'
    ),
    is_inference: r.is_inference === true,
  };
}

const RELIABILITY_LEVELS: readonly ReliabilityLevel[] = [
  'high',
  'medium',
  'low',
];

function asReliabilityLevel(value: unknown): ReliabilityLevel {
  return RELIABILITY_LEVELS.includes(value as ReliabilityLevel)
    ? (value as ReliabilityLevel)
    : 'low';
}

function mapReliability(raw: unknown): FloatingPopulationReliability {
  const r = asRecord(raw);
  return {
    trade_area_count: asNumber(r.trade_area_count),
    covered_trade_areas: asNumber(r.covered_trade_areas),
    level: asReliabilityLevel(r.level),
  };
}

function mapSource(raw: unknown): FloatingPopulationSource {
  const r = asRecord(raw);
  return {
    name: asString(r.name),
    license: asString(r.license),
    period: asString(r.period),
  };
}

const TREND_DIRECTIONS: readonly TrendDirection[] = [
  '증가',
  '감소',
  '보합',
  '판단 불가',
];

function asTrendDirection(value: unknown): TrendDirection {
  return TREND_DIRECTIONS.includes(value as TrendDirection)
    ? (value as TrendDirection)
    : '판단 불가';
}

function mapTrendQuarter(raw: unknown): FloatingPopulationTrendQuarter {
  const r = asRecord(raw);
  return {
    period: asString(r.period),
    daily_avg: asNumber(r.daily_avg),
  };
}

function mapTrend(raw: unknown): FloatingPopulationTrend | null {
  if (!raw) {
    return null;
  }
  const r = asRecord(raw);
  return {
    quarters: asArray(r.quarters).map(mapTrendQuarter),
    direction: asTrendDirection(r.direction),
    qoq_change: asNullableNumber(r.qoq_change),
  };
}

function mapRadiusPoint(raw: unknown): FloatingPopulationRadiusPoint {
  const r = asRecord(raw);
  return {
    radius_m: asNumber(r.radius_m),
    daily_avg: asNumber(r.daily_avg),
  };
}

function mapRadiusProfile(
  raw: unknown
): FloatingPopulationRadiusProfile | null {
  if (!raw) {
    return null;
  }
  const r = asRecord(raw);
  return {
    points: asArray(r.points).map(mapRadiusPoint),
    method: asString(r.method),
  };
}

function mapSelection(raw: unknown): FloatingPopulationSelection {
  const r = asRecord(raw);
  return {
    applied: r.applied === true,
    dropped: asArray(r.dropped).filter(
      (v): v is string => typeof v === 'string'
    ),
    reason: typeof r.reason === 'string' ? r.reason : null,
  };
}

export function adaptFloatingPopulation(
  raw: Record<string, unknown>,
  envelope: Envelope = { status: 'ok', warnings: [] }
): FloatingPopulationData | null {
  // population/benchmark/type/reliability는 화면을 그리는 데 필수인
  // 최상위 필드다 — 이 중 하나라도 객체 형태가 아니면 "우리가 그릴 수 있는
  // 형태가 아니다"로 보고 null을 반환한다(commercial_area의 no_data/error
  // 시 data={}인 경우도 이 조건에서 자연스럽게 걸린다).
  if (
    !raw ||
    typeof raw.population !== 'object' ||
    raw.population === null ||
    typeof raw.benchmark !== 'object' ||
    raw.benchmark === null ||
    typeof raw.type !== 'object' ||
    raw.type === null ||
    typeof raw.reliability !== 'object' ||
    raw.reliability === null
  ) {
    return null;
  }

  return {
    status: envelope.status,
    errorMessage: envelope.errorMessage,
    warnings: envelope.warnings ?? [],
    radius_m: asNumber(raw.radius_m),
    trade_areas: Array.isArray(raw.trade_areas)
      ? raw.trade_areas.map(mapTradeArea)
      : null,
    population: mapPopulation(raw.population),
    benchmark: mapBenchmark(raw.benchmark),
    type: mapType(raw.type),
    reliability: mapReliability(raw.reliability),
    sources: asArray(raw.sources).map(mapSource),
    trend: mapTrend(raw.trend),
    radius_profile: mapRadiusProfile(raw.radius_profile),
    selection: mapSelection(raw.selection),
  };
}
