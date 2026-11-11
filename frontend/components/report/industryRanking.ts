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
  detailTitle?: string;
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
  label: string;
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
    label: `${mockIndustryRankingCodes.length}개 업종`,
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
    const shownSpaceFits = new Set<string>();
    const reasons = renderSegments(
      candidate.reasons_segments,
      facts,
      shownSpaceFits
    ).trim();
    const checks = candidateChecks(candidate, facts, shownSpaceFits);
    const detailTitle = item.aiExcluded
      ? 'AI가 뺀 이유 보기'
      : '추천 이유 보기';
    return reasons || checks.length > 0
      ? { ...item, detailTitle, reasons, checks }
      : item;
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
        'AI가 근거를 보고 빼자고 한 업종과 그 이유예요. 추천 순서는 바꾸지 않았어요.',
      lines: excludedLines,
    },
    {
      title: '규제로 안 되는 업종',
      description:
        '교육환경보호구역 안이라 순위에서 뺀 업종이에요. 절대보호구역(학교 출입문 50m 이내)이면 영업할 수 없고, 상대보호구역(학교 경계 200m 이내)이면 교육청 지역교육환경보호위원회 심의를 거쳐 허용받아야 해요. 어느 구역인지 관할 교육지원청에 먼저 확인하세요.',
      lines: regulationLines,
    },
  ].filter((group) => group.lines.length > 0);

  const excludedCount =
    (result.condition_excluded?.length ?? 0) + regulationLines.length;
  return {
    items,
    groups,
    label: result.ranking?.length
      ? `${items.length}개 순위${excludedCount ? ` · ${excludedCount}개 제외` : ''}`
      : `추천 ${items.length}개`,
    notice: result.ranking?.length
      ? null
      : '이 분석은 전체 순위를 저장하지 않아 추천 업종만 보여 드려요. 다시 분석하면 전체 순위를 볼 수 있어요.',
  };
}
