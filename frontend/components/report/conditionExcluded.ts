import type { ConditionExcludedCandidate } from '@/lib/api/types';

function clause(reason: string, last: boolean): string | null {
  if (reason === '1층이 아님') {
    return last ? '1층이 아니라서' : '1층이 아니고';
  }
  const facility = /^(.+) 설치 불가$/.exec(reason);
  if (facility) {
    return `${facility[1]} 설치가 ${last ? '안 돼서' : '안 되고'}`;
  }
  return null;
}

function because(reasons: string[]): string {
  const clauses = reasons.map((reason, index) =>
    clause(reason, index === reasons.length - 1)
  );
  return clauses.every((text) => text !== null)
    ? clauses.join(' ')
    : `${reasons.join(', ')} 때문에`;
}

export function conditionExcludedLines(
  items: ConditionExcludedCandidate[] | undefined
): string[] | null {
  if (!items || items.length === 0) {
    return null;
  }
  return items.map(
    (item) =>
      `${item.industry_name} — ${because(item.reasons)} 추천에서 뺐어요 (점수로는 ${item.score_rank}위)`
  );
}
