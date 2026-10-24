import { describe, expect, it } from 'vitest';
import { conditionExcludedLines } from './conditionExcluded';

describe('조건 때문에 뺀 업종 문구', () => {
  it('업종·이유·점수상 순위를 한 줄로 쓴다', () => {
    expect(
      conditionExcludedLines([
        {
          industry_code: 'I201',
          industry_name: '한식 음식점',
          reasons: ['배기(덕트) 설치 불가'],
          score_rank: 2,
        },
        {
          industry_code: 'S203',
          industry_name: '자동차 수리·세차',
          reasons: ['1층이 아님', '급배수 설치 불가'],
          score_rank: 7,
        },
      ])
    ).toEqual([
      '한식 음식점 — 배기(덕트) 설치 불가 때문에 추천에서 뺐어요(점수상으로는 2위)',
      '자동차 수리·세차 — 1층이 아님, 급배수 설치 불가 때문에 추천에서 뺐어요(점수상으로는 7위)',
    ]);
  });

  it('빈 목록이나 칸이 없으면 그리지 않는다', () => {
    expect(conditionExcludedLines([])).toBeNull();
    expect(conditionExcludedLines(undefined)).toBeNull();
  });
});
