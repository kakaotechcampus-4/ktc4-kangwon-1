import type { FactSegment, FactView } from '@/lib/api/types';

/**
 * 문장 조각을 화면 문장으로 이어 붙인다.
 * 숫자 형식은 backend/app/agentic/report.py render_segment와 같게 맞춘다 —
 * 서버가 rendered로 미리 만든 요약·추천 이유와 같은 숫자가 나와야 한다.
 */

export type FactIndex = ReadonlyMap<string, FactView>;

export function indexFacts(facts: readonly FactView[]): FactIndex {
  return new Map(facts.map((fact) => [fact.fact_id, fact]));
}

function fixed(value: number, digits: number): string {
  return value.toFixed(digits);
}

// 파이썬 f"{value:,.0f}"처럼 천 단위 쉼표를 넣는다.
function grouped(value: number): string {
  return value.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** fact 하나를 문장에 들어갈 글자로 바꾼다. 값이 없으면 null. */
export function formatFact(
  fact: FactView,
  format: 'count' | 'percent' | 'rate' | 'distance' | 'text'
): string | null {
  const { value, unit } = fact;
  if (value === null) {
    return null;
  }
  if (format === 'text') {
    return typeof value === 'string' ? value : JSON.stringify(value);
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null;
  }
  if (format === 'percent') {
    return `${fixed(unit === '비율' ? value * 100 : value, 1)}%`;
  }
  if (format === 'count') {
    return grouped(value);
  }
  if (format === 'distance') {
    return `${grouped(value)}m`;
  }
  return fixed(value, 2);
}

/** 조각 목록을 한 문장으로. 찾을 수 없는 fact는 '확인 불가'로 표시한다. */
export function renderSegments(
  segments: readonly FactSegment[],
  facts: FactIndex
): string {
  return segments
    .map((segment) => {
      if (segment.type === 'text') {
        return segment.text;
      }
      const fact = facts.get(segment.fact_id);
      return (fact && formatFact(fact, segment.format)) ?? '확인 불가';
    })
    .join('');
}
