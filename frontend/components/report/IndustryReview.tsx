import { INDUSTRIES } from '@/lib/api/industries';
import type { FinalCandidate, LRecord } from '@/lib/api/types';
import { renderSegments, type FactIndex } from '@/lib/api/segments';
import { mockIndustryRecords } from '@/lib/mockData/industryRanking';

/** 기존 리포트 목록 화면에서 쓰는 점수 하한 계산. 순위 목록 UI에는 노출하지 않는다. */
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

type IndustryRank = {
  code: string;
  name: string;
  rank: number;
};

function getRanks(records?: LRecord[]): IndustryRank[] {
  if (records?.length) {
    return records
      .map((record) => ({
        code: record.industry_code,
        name: INDUSTRIES[record.industry_code]?.name ?? record.industry_code,
        rank: record.selection.code_lower_rank,
      }))
      .sort((a, b) => a.rank - b.rank);
  }

  return mockIndustryRecords
    .map((record) => ({
      code: record.industry_code,
      name: INDUSTRIES[record.industry_code]?.name ?? record.industry_code,
      rank: record.selection.code_lower_rank,
    }))
    .sort((a, b) => a.rank - b.rank);
}

export default function IndustryReview({ records }: { records?: LRecord[] }) {
  const industries = getRanks(records);
  const hasCompleteRanks = industries.length === Object.keys(INDUSTRIES).length;
  const isMock = !records?.length;
  const rankGroups = Array.from(
    { length: Math.ceil(industries.length / 10) },
    (_, index) => industries.slice(index * 10, (index + 1) * 10)
  );

  return (
    <section className="industry-ranking" aria-label="업종 검토 순위">
      <header className="industry-ranking-header">
        <p>
          {isMock
            ? '화면 예시 순위입니다. 실제 분석 결과에서는 순위가 달라질 수 있으며, 업종을 살펴볼 때 참고하는 정보예요.'
            : '이 순위는 업종을 검토할 때 참고하는 순서예요. 순위가 높다고 입점이 확정되거나 상위 업종만 적합하다는 뜻은 아닙니다. 순위 차이가 크지 않을 수 있으니 관심 업종의 분석 근거와 조건도 함께 확인해 보세요.'}
        </p>
        <span>
          {hasCompleteRanks ? '전체 51개 업종' : `${industries.length}개 업종`}
        </span>
      </header>

      <div className="industry-ranking-groups">
        {rankGroups.map((group) => {
          const firstRank = group[0]?.rank ?? 0;
          const lastRank = group[group.length - 1]?.rank ?? firstRank;

          return (
            <section
              className="industry-ranking-group"
              key={`${firstRank}-${lastRank}`}
              aria-label={`${firstRank}위부터 ${lastRank}위`}
            >
              <h3 className="industry-ranking-range">
                {String(firstRank).padStart(2, '0')}–
                {String(lastRank).padStart(2, '0')}
              </h3>
              <ol className="industry-ranking-list" start={firstRank}>
                {group.map((industry) => (
                  <li key={industry.code}>
                    <span
                      className="industry-ranking-number"
                      aria-label={`${industry.rank}위`}
                    >
                      {String(industry.rank).padStart(2, '0')}
                    </span>
                    <span className="industry-ranking-name">
                      {industry.name}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          );
        })}
      </div>
    </section>
  );
}
