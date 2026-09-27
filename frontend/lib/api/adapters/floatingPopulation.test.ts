import { describe, expect, it } from 'vitest';
import { adaptFloatingPopulation } from '@/lib/api/adapters/floatingPopulation';

// backend/app/agents/floating_population/schemas.py의 FloatingPopulationData
// 형태(snake_case)를 그대로 흉내낸 샘플. 실제 필드 이름을 그대로 써서,
// 어댑터가 스키마가 바뀌면 눈에 보이게 깨지도록 한다.
const rawSample: Record<string, unknown> = {
  description: '테스트 유동인구 설명',
  period_code: '20262',
  radius_m: 500,
  trade_areas: [
    { code: 'TA01', name: '후평동먹자골목', kind: '골목상권', distance_m: 120 },
  ],
  population: {
    unit: '명',
    share_unit: '비율',
    daily_avg: 4820,
    female_ratio: 0.52,
    by_age: null,
    age_share: { '10': 0.05, '20': 0.15, '60': 0.17 },
    by_time: null,
    time_per_hour_share: { '00_06': 0.06, '17_21': 0.28 },
    peak_time_band: '17_21',
    by_day: null,
    weekend_to_weekday_ratio: 1.12,
  },
  benchmark: {
    unit: '배수',
    baseline: '서울 평균',
    age_index: { '10': 0.85, '20': 0.62 },
    time_per_hour_index: { '00_06': 0.36 },
    lunch_index: 0.92,
    evening_index: 1.35,
    night_index: 1.15,
    weekend_index: 1.18,
    mean_daily_per_trade_area: 803.3,
    scale_percentile: 58,
  },
  type: {
    label: '주거생활형',
    is_inference: true,
    signals_unit: '비율',
    reasons: ['40·50대 합이 46%로 가장 큰 비중을 차지합니다.'],
    signals: { age_4050_share: 0.46 },
    thresholds: { age_4050_share: 0.4 },
    rules_version: 'v1',
  },
  reliability: {
    trade_area_count: 6,
    covered_trade_areas: 6,
    level: 'high',
  },
  trend: {
    unit: '명/일',
    quarters: [
      {
        period_code: '20253',
        period: '2025년 3분기',
        daily_avg: 4460,
        trade_area_count: 6,
        age_share: {},
        time_per_hour_share: {},
      },
      {
        period_code: '20262',
        period: '2026년 2분기',
        daily_avg: 4820,
        trade_area_count: 6,
        age_share: {},
        time_per_hour_share: {},
      },
    ],
    qoq_change: -4.6,
    yoy_change: null,
    direction: '보합',
  },
  radius_profile: {
    unit: '명',
    method:
      '반경 안과 겹치는 상권의 길단위인구를 면적 비례로 안분해 추정했습니다.',
    points: [
      {
        radius_m: 50,
        total: 210,
        daily_avg: 210,
        trade_area_count: 1,
        effective_trade_areas: 0.4,
      },
      {
        radius_m: 500,
        total: 4820,
        daily_avg: 4820,
        trade_area_count: 6,
        effective_trade_areas: 3.1,
      },
    ],
  },
  selection: {
    applied: false,
    selectable: ['trend', 'radius_profile', 'trade_areas'],
    included: ['trend', 'radius_profile', 'trade_areas'],
    dropped: [],
    reason: null,
    unavailable_reason: null,
  },
  sources: [
    {
      name: '소상공인시장진흥공단 상권정보(유동인구)',
      url: 'https://example.com',
      license: '공공누리 1유형',
      period: '2026년 2분기',
    },
  ],
};

describe('adaptFloatingPopulation', () => {
  it('snake_case 원본을 같은 이름의 FloatingPopulationData로 안전하게 옮긴다', () => {
    const result = adaptFloatingPopulation(rawSample, {
      status: 'ok',
      warnings: [],
    });

    expect(result).not.toBeNull();
    expect(result?.status).toBe('ok');
    expect(result?.radius_m).toBe(500);
    expect(result?.population).toEqual({
      daily_avg: 4820,
      female_ratio: 0.52,
      age_share: { '10': 0.05, '20': 0.15, '60': 0.17 },
      time_per_hour_share: { '00_06': 0.06, '17_21': 0.28 },
      peak_time_band: '17_21',
      weekend_to_weekday_ratio: 1.12,
    });
    expect(result?.benchmark).toEqual({
      age_index: { '10': 0.85, '20': 0.62 },
      lunch_index: 0.92,
      evening_index: 1.35,
      night_index: 1.15,
      weekend_index: 1.18,
      scale_percentile: 58,
    });
    expect(result?.type).toEqual({
      label: '주거생활형',
      reasons: ['40·50대 합이 46%로 가장 큰 비중을 차지합니다.'],
      is_inference: true,
    });
    expect(result?.reliability).toEqual({
      trade_area_count: 6,
      covered_trade_areas: 6,
      level: 'high',
    });
    expect(result?.trade_areas).toEqual([
      { name: '후평동먹자골목', kind: '골목상권' },
    ]);
    expect(result?.sources).toEqual([
      {
        name: '소상공인시장진흥공단 상권정보(유동인구)',
        license: '공공누리 1유형',
        period: '2026년 2분기',
      },
    ]);
  });

  it('trend/radius_profile을 null 안전하게 옮긴다', () => {
    const result = adaptFloatingPopulation(rawSample);

    expect(result?.trend).toEqual({
      quarters: [
        { period: '2025년 3분기', daily_avg: 4460 },
        { period: '2026년 2분기', daily_avg: 4820 },
      ],
      direction: '보합',
      qoq_change: -4.6,
    });
    expect(result?.radius_profile).toEqual({
      points: [
        { radius_m: 50, daily_avg: 210 },
        { radius_m: 500, daily_avg: 4820 },
      ],
      method:
        '반경 안과 겹치는 상권의 길단위인구를 면적 비례로 안분해 추정했습니다.',
    });
  });

  it('trend가 null이면(분기 2개 미만) 그대로 null을 옮긴다', () => {
    const result = adaptFloatingPopulation({ ...rawSample, trend: null });

    expect(result?.trend).toBeNull();
  });

  it('radius_profile이 null이면 그대로 null을 옮긴다', () => {
    const result = adaptFloatingPopulation({
      ...rawSample,
      radius_profile: null,
    });

    expect(result?.radius_profile).toBeNull();
  });

  it('trade_areas가 null이면 그대로 null을 옮긴다(과거 선별로 생략된 경우)', () => {
    const result = adaptFloatingPopulation({ ...rawSample, trade_areas: null });

    expect(result?.trade_areas).toBeNull();
  });

  it('population/benchmark/type/reliability 중 하나라도 없으면 null을 반환한다', () => {
    const missingPopulation = adaptFloatingPopulation({
      ...rawSample,
      population: undefined,
    });
    const missingBenchmark = adaptFloatingPopulation({
      ...rawSample,
      benchmark: null,
    });
    const missingType = adaptFloatingPopulation({
      ...rawSample,
      type: undefined,
    });
    const missingReliability = adaptFloatingPopulation({
      ...rawSample,
      reliability: undefined,
    });

    expect(missingPopulation).toBeNull();
    expect(missingBenchmark).toBeNull();
    expect(missingType).toBeNull();
    expect(missingReliability).toBeNull();
  });

  it('빈 객체({}, no_data/error 상태의 data)를 넣으면 null을 반환한다', () => {
    const result = adaptFloatingPopulation(
      {},
      { status: 'no_data', warnings: ['자료 없음'] }
    );

    expect(result).toBeNull();
  });

  it('envelope을 안 넘기면 status ok/warnings 빈 배열로 기본 처리한다', () => {
    const result = adaptFloatingPopulation(rawSample);

    expect(result?.status).toBe('ok');
    expect(result?.warnings).toEqual([]);
  });
});
