import { describe, expect, it } from 'vitest';
import { formatFact } from './segments';
import type { FactView, JsonValue } from './types';

function fact(metric: string, value: JsonValue): FactView {
  return {
    fact_id: 'f',
    source: 'user',
    metric,
    value,
    unit: '확인 화면 확정값',
    period: '',
    spatial_scope: {},
    industry_code: null,
    status: 'observed',
    citable: true,
    calc_version: '',
    provenance_ref: '',
  };
}

describe('fact 글자 변환', () => {
  it('확인 화면 시설 값은 한국어로 읽는다', () => {
    expect(
      formatFact(
        fact('existing_facilities', {
          ventilation: 'unavailable',
          kitchen: 'present',
          water_supply: 'installable',
        }),
        'text'
      )
    ).toBe('주방 있음 · 배기(덕트) 설치 불가 · 급배수 설치 가능');
  });

  it('임대인이 글로 쓴 시설 답은 그대로 둔다', () => {
    expect(formatFact(fact('existing_facilities', '배기 없음'), 'text')).toBe(
      '배기 없음'
    );
  });
});
