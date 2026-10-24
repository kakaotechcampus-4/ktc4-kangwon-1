import type { ConditionExcludedCandidate } from '@/lib/api/types';

export function conditionExcludedLines(
  items: ConditionExcludedCandidate[] | undefined
): string[] | null {
  if (!items || items.length === 0) {
    return null;
  }
  return items.map(
    (item) =>
      `${item.industry_name} — ${item.reasons.join(', ')} 때문에 추천에서 뺐어요(점수상으로는 ${item.score_rank}위)`
  );
}
