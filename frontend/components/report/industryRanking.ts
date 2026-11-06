import { candidateChecks } from '@/lib/api/candidates';
import { INDUSTRIES } from '@/lib/api/industries';
import { renderSegments, type FactIndex } from '@/lib/api/segments';
import type { DecisionResult } from '@/lib/api/types';
import { mockIndustryRankingCodes } from '@/lib/mockData/reportPresentation';
import { conditionExcludedLines } from './conditionExcluded';

const DETAIL_RANKS = 5;

export type RankingItem = {
  rank: number;
  name: string;
  aiExcluded: boolean;
  reasons?: string;
  checks?: string[];
};

export type RankingGroup = {
  title: string;
  description: string;
  lines: string[];
};

export type RankingView = {
  items: RankingItem[];
  groups: RankingGroup[];
  notice: string | null;
};

export function mockRankingView(): RankingView {
  return {
    items: mockIndustryRankingCodes.map((code, index) => ({
      rank: index + 1,
      name: INDUSTRIES[code].name,
      aiExcluded: false,
    })),
    groups: [],
    notice: null,
  };
}

export function rankingView(
  result: DecisionResult,
  facts: FactIndex
): RankingView {
  const candidates = new Map(
    result.top5.map((candidate) => [candidate.industry_code, candidate])
  );
  const aiExcluded = new Set(
    result.excluded_candidates.map((candidate) => candidate.industry_code)
  );
  const ranked = result.ranking?.length
    ? result.ranking.map((item) => ({
        rank: item.rank,
        code: item.industry_code,
        name: item.industry_name,
        aiExcluded: item.ai_excluded,
      }))
    : result.top5.map((candidate, index) => ({
        rank: index + 1,
        code: candidate.industry_code,
        name: candidate.industry_name,
        aiExcluded: aiExcluded.has(candidate.industry_code),
      }));

  const items = ranked.map(({ code, ...item }): RankingItem => {
    const candidate =
      item.rank <= DETAIL_RANKS ? candidates.get(code) : undefined;
    if (!candidate) {
      return item;
    }
    const reasons = renderSegments(candidate.reasons_segments, facts).trim();
    const checks = candidateChecks(candidate, facts);
    return reasons || checks.length > 0 ? { ...item, reasons, checks } : item;
  });

  const excludedLines = result.excluded_candidates.map((candidate) => {
    const why = renderSegments(
      candidate.reasons_segments.length > 0
        ? candidate.reasons_segments
        : candidate.risks_segments,
      facts
    ).trim();
    return why
      ? `${candidate.industry_name} — ${why}`
      : candidate.industry_name;
  });
  const regulationLines = (result.regulation_excluded ?? []).map(
    (item) => item.industry_name
  );
  const groups: RankingGroup[] = [
    {
      title: '조건 때문에 뺀 업종',
      description:
        '확인 화면에서 고른 층·설비로는 들어오기 어려워 순위에서 뺀 업종이에요.',
      lines: conditionExcludedLines(result.condition_excluded) ?? [],
    },
    {
      title: '제외한 업종',
      description:
        'AI가 근거를 보고 빼자고 한 업종이에요. 순위에는 그대로 남겨 두었어요.',
      lines: excludedLines,
    },
    {
      title: '규제로 안 되는 업종',
      description:
        '규제 확인에서 이 자리에서는 영업할 수 없다고 나온 업종이에요.',
      lines: regulationLines,
    },
  ].filter((group) => group.lines.length > 0);

  return {
    items,
    groups,
    notice: result.ranking?.length
      ? null
      : '이 분석은 전체 순위를 저장하지 않아 추천 업종만 보여 드려요. 다시 분석하면 전체 순위를 볼 수 있어요.',
  };
}
