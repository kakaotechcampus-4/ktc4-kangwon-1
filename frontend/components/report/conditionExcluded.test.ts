import { describe, expect, it } from 'vitest';
import { conditionExcludedLines } from './conditionExcluded';

describe('조건 때문에 뺀 업종 문구', () => {
  it('이유를 말로 풀어 한 줄로 쓴다', () => {
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
        {
          industry_code: 'S204',
          industry_name: '모터사이클 수리',
          reasons: ['1층이 아님'],
          score_rank: 9,
        },
      ])
    ).toEqual([
      '한식 음식점 — 배기(덕트) 설치가 안 돼서 추천에서 뺐어요 (점수로는 2위)',
      '자동차 수리·세차 — 1층이 아니고 급배수 설치가 안 돼서 추천에서 뺐어요 (점수로는 7위)',
      '모터사이클 수리 — 1층이 아니라서 추천에서 뺐어요 (점수로는 9위)',
    ]);
  });

  it('모르는 이유는 그대로 적는다', () => {
    expect(
      conditionExcludedLines([
        {
          industry_code: 'I201',
          industry_name: '한식 음식점',
          reasons: ['새 조건'],
          score_rank: 3,
        },
      ])
    ).toEqual(['한식 음식점 — 새 조건 때문에 추천에서 뺐어요 (점수로는 3위)']);
  });

  it('빈 목록이나 칸이 없으면 그리지 않는다', () => {
    expect(conditionExcludedLines([])).toBeNull();
    expect(conditionExcludedLines(undefined)).toBeNull();
  });
});
