import { describe, expect, it } from 'vitest';
import { educationZoneStatus } from '@/lib/api/educationZone';
import type { FactView } from '@/lib/api/types';

const fact = (overrides: Partial<FactView>): FactView =>
  ({
    fact_id: 'f-1',
    source: 'regulation',
    metric: 'zone_contains',
    value: true,
    unit: '포함 여부',
    period: '2026-11-04T00:00:00+00:00',
    spatial_scope: {},
    industry_code: null,
    status: 'observed',
    citable: true,
    calc_version: 'v1',
    provenance_ref: 'r-1',
    ...overrides,
  }) as FactView;

describe('educationZoneStatus', () => {
  it('확인된 포함 fact는 보호구역 안이다', () => {
    expect(educationZoneStatus([fact({})])).toBe('inside');
  });

  it('확인된 비포함 fact는 보호구역 밖이다', () => {
    expect(educationZoneStatus([fact({ value: false })])).toBe('outside');
  });

  it('확인하지 못했거나 fact가 없으면 모름으로 둔다', () => {
    expect(
      educationZoneStatus([fact({ status: 'unknown', value: null })])
    ).toBe('unknown');
    expect(educationZoneStatus([])).toBe('unknown');
  });

  it('다른 출처·지표의 fact는 보지 않는다', () => {
    expect(educationZoneStatus([fact({ source: 'map' })])).toBe('unknown');
    expect(educationZoneStatus([fact({ metric: 'distance_m' })])).toBe(
      'unknown'
    );
  });
});
