import { INDUSTRIES } from '@/lib/api/industries';

const RANKS_PER_COLUMN = 17;

/** 백엔드 카탈로그를 기준으로 한 전체 업종 순위 화면용 목업 목록. */
const rankedIndustries = Object.values(INDUSTRIES).map((industry, index) => ({
  rank: index + 1,
  name: industry.name,
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

export default function IndustryRankingList() {
  return (
    <section className="industry-ranking" aria-label="51개 업종 순위 목업">
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
