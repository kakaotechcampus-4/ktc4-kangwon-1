import { describe, expect, it } from 'vitest';
import {
  competitionFromFacts,
  floatingPopulationFromFacts,
  formatPeriod,
  lifecycleFromFacts,
} from './facts';
import { indexFacts, renderSegments } from '@/lib/api/segments';
import type { FactView, JsonValue } from '@/lib/api/types';

let id = 0;
function fact(
  source: FactView['source'],
  metric: string,
  value: JsonValue,
  {
    industry = null,
    unit = '배수',
    period = '20262',
    status = 'observed',
  }: {
    industry?: string | null;
    unit?: string;
    period?: string;
    status?: FactView['status'];
  } = {}
): FactView {
  id += 1;
  return {
    fact_id: `f_${String(id).padStart(8, '0')}-0000-4000-8000-000000000000`,
    source,
    metric,
    value: status === 'observed' ? value : null,
    unit,
    period,
    spatial_scope: {
      radius_m: 500,
      comparison_radius_m: 2000,
      selected_trade_area_codes: ['3110509', '3110560'],
    },
    industry_code: industry,
    status,
    citable: status === 'observed',
    calc_version: 'test',
    provenance_ref: 'local_fact_lineage:test',
  };
}

describe('formatPeriod', () => {
  it('분기 코드를 읽을 수 있는 글자로 바꾼다', () => {
    expect(formatPeriod('20262')).toBe('2026년 2분기');
    expect(formatPeriod('20252~20262')).toBe('2025년 2분기~2026년 2분기');
  });
});

describe('renderSegments', () => {
  it('백엔드 render_segment와 같은 형식으로 숫자를 넣는다', () => {
    const share = fact('floating_population', 'yoy_change', 0.0173, {
      unit: '비율',
    });
    const count = fact('commercial_area', 'store_count', 12345, { unit: '개' });
    const facts = indexFacts([share, count]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '점포 ' },
          { type: 'fact', fact_id: count.fact_id, format: 'count' },
          { type: 'text', text: '개, 증가율 ' },
          { type: 'fact', fact_id: share.fact_id, format: 'percent' },
          { type: 'text', text: ', 배수 ' },
          { type: 'fact', fact_id: share.fact_id, format: 'rate' },
        ],
        facts
      )
    ).toBe('점포 12,345개, 증가율 1.7%, 배수 0.02');
  });

  it('없는 fact는 숫자를 지어내지 않고 확인 불가로 둔다', () => {
    expect(
      renderSegments(
        [{ type: 'fact', fact_id: 'f_missing', format: 'count' }],
        indexFacts([])
      )
    ).toBe('확인 불가');
  });
});

describe('floatingPopulationFromFacts', () => {
  const facts = [
    fact('floating_population', 'mean_daily_per_trade_area', 14493.5, {
      unit: '명/일·상권 1곳',
      period: '20252~20262',
    }),
    fact(
      'floating_population',
      'by_time',
      {
        '00_06': 600,
        '06_11': 500,
        '11_14': 300,
        '14_17': 300,
        '17_21': 800,
        '21_24': 300,
      },
      { unit: '분기 통행량' }
    ),
    fact(
      'floating_population',
      'age_share',
      { '20': 0.3, '10': 0.1, '60': 0.6 },
      {
        unit: '비율',
      }
    ),
    fact('floating_population', 'weekend_index', 1.126),
    // 업종별 지표는 지역 전체 값으로 쓰지 않는다.
    fact('floating_population', 'yoy_change', 0.5, { industry: 'I201' }),
  ];

  it('구간 길이로 나눈 시간당 비중과 연령 비율을 만든다', () => {
    const data = floatingPopulationFromFacts(facts);
    expect(data).not.toBeNull();
    expect(data?.radiusM).toBe(500);
    expect(data?.tradeAreaCount).toBe(2);
    expect(data?.period).toBe('2025년 2분기~2026년 2분기');
    // 시간당 값은 모두 100이고 17~21시만 200 → 비중 1/7, 2/7
    expect(data?.timeBands.map((band) => band.share * 7)).toEqual(
      [1, 1, 1, 1, 2, 1].map((value) => expect.closeTo(value, 6))
    );
    expect(data?.ageShares.map((age) => age.label)).toEqual([
      '10대',
      '20대',
      '60대 이상',
    ]);
    expect(data?.yoyChange).toBeNull();
    expect(data?.weekendIndex).toBe(1.126);
  });

  it('유동인구 fact가 없으면 null', () => {
    expect(floatingPopulationFromFacts([])).toBeNull();
  });
});

describe('competitionFromFacts', () => {
  const facts = [
    fact('commercial_area', 'store_count', 30, {
      industry: 'I201',
      unit: '개',
    }),
    fact('commercial_area', 'store_count', 10, {
      industry: 'G204',
      unit: '개',
    }),
    fact('commercial_area', 'density_per_km2', 38.2, { industry: 'I201' }),
    fact('commercial_area', 'lq', 1.21, { industry: 'I201' }),
    fact('commercial_area', 'competition_index', null, {
      industry: 'I201',
      status: 'unknown',
    }),
  ];

  it('합계·다양성·고른 업종 행을 만들고 미확인 값은 null로 둔다', () => {
    const data = competitionFromFacts(facts, ['I201', 'S207']);
    expect(data?.storeTotal).toBe(40);
    // 점포 비중 0.75, 0.25 → 1 / (0.5625 + 0.0625) = 1.6
    expect(data?.effectiveCategories).toBeCloseTo(1.6);
    expect(data?.comparisonRadiusM).toBe(2000);
    expect(data?.topByCount.map((row) => row.code)).toEqual(['I201', 'G204']);
    expect(data?.selected[0]).toMatchObject({
      code: 'I201',
      storeCount: 30,
      densityPerKm2: 38.2,
      lq: 1.21,
      competitionIndex: null,
    });
    // 점포 자료가 없는 업종도 행은 남기고 값만 비운다.
    expect(data?.selected[1]).toMatchObject({ code: 'S207', storeCount: null });
  });

  it('점포 수 fact가 없으면 null', () => {
    expect(competitionFromFacts([], ['I201'])).toBeNull();
  });
});

describe('lifecycleFromFacts', () => {
  it('고른 업종의 폐업률·회전율·순증감을 모은다', () => {
    const data = lifecycleFromFacts(
      [
        fact('business_lifecycle', 'recent_year_close_rate', 12.5, {
          industry: 'I201',
          unit: '%',
          period: '20233~20262',
        }),
        fact('business_lifecycle', 'net_change_rate', -3.12, {
          industry: 'I201',
          unit: '%',
        }),
      ],
      ['I201']
    );
    expect(data?.period).toBe('2023년 3분기~2026년 2분기');
    expect(data?.rows).toEqual([
      {
        code: 'I201',
        name: expect.any(String),
        avgStoreCount: null,
        recentCloseRate: 12.5,
        closeRateRatio: null,
        turnoverRate: null,
        netChangeRate: -3.12,
      },
    ]);
  });
});
