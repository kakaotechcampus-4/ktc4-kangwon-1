import type { FinalCandidate } from '@/lib/api/types';
import { renderSegments, type FactIndex } from '@/lib/api/segments';

/** 새 결과는 코드 90점과 L을 합산한다. 구 결과는 기존 관측 점수 구간을 표시한다. */
export function candidateScore(candidate: FinalCandidate): {
  low: number;
  high: number;
} | null {
  if (candidate.calculation) {
    const low = candidate.calculation.ranking_points;
    return {
      low: Math.round(low),
      high: Math.round(candidate.L_status === 'unknown' ? low + 10 : low),
    };
  }
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
