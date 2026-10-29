import { describe, expect, it } from 'vitest';
import { formatFact, indexFacts, renderSegments } from './segments';
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

  it('공간 비교 결과는 JSON 대신 필요한 조건만 읽는다', () => {
    expect(
      formatFact(
        fact('space_fit', {
          area: '불일치',
          confidence: 'low',
          floor: '해당 없음',
          kitchen: '해당 없음',
          reviewed: true,
          ventilation: '미확인',
          water_supply: '해당 없음',
        }),
        'text'
      )
    ).toBe('면적 불일치 · 배기(덕트) 미확인');
  });

  it('읽는 법을 모르는 객체는 문장에 JSON으로 새지 않는다', () => {
    expect(formatFact(fact('unknown_metric', { a: 1 }), 'text')).toBe('');
  });

  it('문장이 끝난 뒤 붙는 값은 한 칸 띄운다', () => {
    expect(
      renderSegments(
        [
          { type: 'text', text: '공간 확인이 필요합니다.' },
          { type: 'fact', fact_id: 'f', format: 'text' },
        ],
        indexFacts([fact('space_fit', { area: '불일치' })])
      )
    ).toBe('공간 확인이 필요합니다. 면적 불일치');
  });
});
