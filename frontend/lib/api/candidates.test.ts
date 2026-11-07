import { describe, expect, it } from 'vitest';
import type { FinalCandidate } from '@/lib/api/types';
import { candidateScore } from '@/lib/api/candidates';

describe('candidateScore', () => {
  it('새 추천 점수와 원래 관측 점수 구간을 섞지 않는다', () => {
    const candidate = {
      lower_ratio: 0.4,
      upper_ratio: 0.8,
      L_status: 'unknown',
      calculation: { ranking_points: 65 },
    } as FinalCandidate;
    expect(candidateScore(candidate)).toEqual({ low: 65, high: 75 });
    expect(candidateScore({ ...candidate, calculation: null })).toEqual({
      low: 40,
      high: 80,
    });
    expect(
      candidateScore({
        ...candidate,
        L_status: 'observed',
        L_points: 5,
        calculation: { ...candidate.calculation!, ranking_points: 70 },
      })
    ).toEqual({ low: 70, high: 70 });
  });
});
