import { describe, expect, it } from 'vitest';
import { formatFact, indexFacts, renderSegments } from './segments';
import type { FactView, JsonValue } from './types';

function fact(metric: string, value: JsonValue, factId = 'f'): FactView {
  return {
    fact_id: factId,
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

  it('공간 비교 값은 해당 없는 칸을 빼고 한국어로 읽는다', () => {
    expect(
      formatFact(
        fact('space_fit', {
          area: '일치',
          confidence: 'low',
          floor: '해당 없음',
          kitchen: '해당 없음',
          reviewed: true,
          ventilation: '미확인',
          water_supply: '불일치',
        }),
        'text'
      )
    ).toBe('면적 일치 · 배기(덕트) 미확인 · 급배수 불일치 (비교 신뢰도 낮음)');
  });

  it('그 밖의 묶음 값은 날것으로 보이지 않는다', () => {
    expect(formatFact(fact('age_share', { '20': 0.3 }), 'text')).toBeNull();
  });
});

describe('문장 조각 잇기', () => {
  it('문장 끝 뒤와 근거 값 사이에 빈칸을 넣는다', () => {
    const facts = indexFacts([
      fact('exclusive_area', '85㎡', 'a'),
      fact('floor', '1층', 'b'),
    ]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '후보군입니다.' },
          { type: 'fact', fact_id: 'a', format: 'text' },
          { type: 'fact', fact_id: 'b', format: 'text' },
        ],
        facts
      )
    ).toBe('후보군입니다. 85㎡ 1층');
  });

  it('문장 안의 숫자는 붙여 둔다', () => {
    const facts = indexFacts([fact('store_total', 1200, 'a')]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '점포는 ' },
          { type: 'fact', fact_id: 'a', format: 'count' },
          { type: 'text', text: '곳입니다.' },
        ],
        facts
      )
    ).toBe('점포는 1,200곳입니다.');
  });
});
