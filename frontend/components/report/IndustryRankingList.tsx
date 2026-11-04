import { INDUSTRIES } from '@/lib/api/industries';
import { mockIndustryRankingCodes } from '@/lib/mockData/reportPresentation';

const RANKS_PER_COLUMN = 17;

/** 백엔드 카탈로그를 기준으로 한 전체 업종 순위 화면용 목업 목록. */
const rankedIndustries = mockIndustryRankingCodes.map((code, index) => ({
  rank: index + 1,
  name: INDUSTRIES[code].name,
}));

const rankGroups = Array.from(
  { length: Math.ceil(rankedIndustries.length / RANKS_PER_COLUMN) },
  (_, index) => {
    const items = rankedIndustries.slice(
      index * RANKS_PER_COLUMN,
      (index + 1) * RANKS_PER_COLUMN
    );

    return {
      start: items[0]?.rank ?? 0,
      end: items.at(-1)?.rank ?? 0,
      items,
    };
  }
);

export default function IndustryRankingList({
  totalCount,
}: {
  totalCount: number;
}) {
  const firstTen = rankedIndustries.slice(0, 10);
  const remaining = rankedIndustries.slice(10);
  return (
    <section className="industry-ranking" aria-label="51개 업종 순위 목업">
      <div className="industry-ranking-mobile">
        <div className="industry-ranking-mobile-heading-row">
          <h3 className="industry-ranking-mobile-heading">먼저 검토할 업종</h3>
          <span className="industry-ranking-mobile-count">
            {totalCount}개 업종
          </span>
        </div>
        <ol className="industry-ranking-list" start={1}>
          {firstTen.map((industry) => (
            <li key={industry.rank}>
              <span className="industry-ranking-number" aria-hidden="true">
                {String(industry.rank).padStart(2, '0')}
              </span>
              <span className="industry-ranking-name">{industry.name}</span>
            </li>
          ))}
        </ol>
        {remaining.length > 0 && (
          <details className="industry-ranking-more">
            <summary>나머지 업종 {remaining.length}개 보기</summary>
            <ol className="industry-ranking-list" start={11}>
              {remaining.map((industry) => (
                <li key={industry.rank}>
                  <span className="industry-ranking-number" aria-hidden="true">
                    {String(industry.rank).padStart(2, '0')}
                  </span>
                  <span className="industry-ranking-name">{industry.name}</span>
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
      <div className="industry-ranking-groups">
        {rankGroups.map((group) => (
          <section
            className="industry-ranking-group"
            key={`${group.start}-${group.end}`}
            aria-label={`${group.start}위부터 ${group.end}위`}
          >
            <h3 className="industry-ranking-range">
              {String(group.start).padStart(2, '0')} —{' '}
              {String(group.end).padStart(2, '0')}
            </h3>
            <ol className="industry-ranking-list" start={group.start}>
              {group.items.map((industry) => (
                <li key={industry.rank}>
                  <span className="industry-ranking-number" aria-hidden="true">
                    {String(industry.rank).padStart(2, '0')}
                  </span>
                  <span className="industry-ranking-name">{industry.name}</span>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </section>
  );
}
