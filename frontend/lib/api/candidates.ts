import type { FinalCandidate } from '@/lib/api/types';
import { renderSegments, type FactIndex } from '@/lib/api/segments';

/** 100점 환산 점수 구간. 적용 배점(A)이 0이면 점수를 매길 수 없다. */
export function candidateScore(candidate: FinalCandidate): {
  low: number;
  high: number;
} | null {
  if (candidate.lower_ratio === null || candidate.upper_ratio === null) {
    return null;
  }
  return {
    low: Math.round(candidate.lower_ratio * 100),
    high: Math.round(candidate.upper_ratio * 100),
  };
}

/** 입점 전 확인할 문장 — 위험 요인, 확인 조건 문장, 서버가 붙인 확인 조건 순서. */
export function candidateChecks(
  candidate: FinalCandidate,
  facts: FactIndex
): string[] {
  const sentences = [
    renderSegments(candidate.risks_segments, facts),
    renderSegments(candidate.confirmation_conditions_segments, facts),
    ...candidate.confirmation_conditions,
  ].map((text) => text.trim());
  return [...new Set(sentences.filter(Boolean))];
}
