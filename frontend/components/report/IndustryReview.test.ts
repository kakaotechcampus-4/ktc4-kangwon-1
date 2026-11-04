import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FinalCandidate } from '@/lib/api/types';
import IndustryReview, { candidateScore } from './IndustryReview';

describe('검토 후보 업종 안내', () => {
  it('숨은 공간 조정이 있으니 점수 순서라고 쓰지 않는다', () => {
    const html = renderToStaticMarkup(
      createElement(IndustryReview, { top5: [], excluded: [] })
    );
    expect(html).toContain('추천 순서입니다. 배지와 확인 조건을 함께 보세요');
    expect(html).not.toContain('점수가 높은 순서');
  });

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
