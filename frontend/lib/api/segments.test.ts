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

  it('공간 비교 문구 뒤에 오는 문장은 띄운다', () => {
    const facts = indexFacts([
      fact('space_fit', { area: '일치', confidence: 'low' }, 'a'),
    ]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '낮습니다.' },
          { type: 'fact', fact_id: 'a', format: 'text' },
          { type: 'text', text: '학원을 찾는' },
        ],
        facts
      )
    ).toBe('낮습니다. 면적 일치 (비교 신뢰도 낮음) 학원을 찾는');
  });

  it('공간 비교 문구 뒤 문장부호는 띄우지 않는다', () => {
    const facts = indexFacts([
      fact('space_fit', { area: '일치', confidence: 'low' }, 'a'),
    ]);
    expect(
      renderSegments(
        [
          { type: 'fact', fact_id: 'a', format: 'text' },
          { type: 'text', text: '.' },
        ],
        facts
      )
    ).toBe('면적 일치 (비교 신뢰도 낮음).');
  });

  it('괄호로 끝나는 다른 값 뒤 조사는 붙여 둔다', () => {
    const facts = indexFacts([fact('place_name', '스타벅스(강남점)', 'a')]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '근처에 ' },
          { type: 'fact', fact_id: 'a', format: 'text' },
          { type: 'text', text: '이 있습니다.' },
        ],
        facts
      )
    ).toBe('근처에 스타벅스(강남점)이 있습니다.');
  });

  it('앞뒤 빈칸이 지워진 글 뒤 숫자는 띄운다', () => {
    const facts = indexFacts([fact('store_total', 1200, 'a')]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '점포는' },
          { type: 'fact', fact_id: 'a', format: 'count' },
          { type: 'text', text: '곳입니다.' },
        ],
        facts
      )
    ).toBe('점포는 1,200곳입니다.');
  });

  it('괄호 안 숫자는 붙여 둔다', () => {
    const facts = indexFacts([fact('store_total', 1200, 'a')]);
    expect(
      renderSegments(
        [
          { type: 'text', text: '(' },
          { type: 'fact', fact_id: 'a', format: 'count' },
          { type: 'text', text: ')' },
        ],
        facts
      )
    ).toBe('(1,200)');
  });

  it('글 조각 둘 사이는 띄운다', () => {
    expect(
      renderSegments(
        [
          { type: 'text', text: '표본이 작음' },
          { type: 'text', text: '서울 밖 점포 미반영.' },
        ],
        indexFacts([])
      )
    ).toBe('표본이 작음 서울 밖 점포 미반영.');
  });
});

describe('서버와 같은 글자', () => {
  it('목록 값은 쉼표로 잇는다', () => {
    expect(formatFact(fact('x', ['카페', '학원']), 'text')).toBe('카페, 학원');
  });

  it('참거짓은 예·아니요로 읽는다', () => {
    expect(formatFact(fact('x', true), 'text')).toBe('예');
    expect(formatFact(fact('x', false), 'text')).toBe('아니요');
  });

  it('딱 중간인 값은 0에서 먼 쪽으로 반올림한다', () => {
    const ratio = { ...fact('x', 0.0625), unit: '비율' };
    expect(formatFact(ratio, 'percent')).toBe('6.3%');
    expect(formatFact(fact('x', 12.5), 'distance')).toBe('13m');
    expect(formatFact(fact('x', 0.125), 'rate')).toBe('0.13');
    expect(formatFact(fact('x', 1.005), 'rate')).toBe('1.00');
  });
});
