import type { RankingItem, RankingView } from './industryRanking';

const RANKS_PER_COLUMN = 17;

function rankGroups(items: RankingItem[]) {
  return Array.from(
    { length: Math.ceil(items.length / RANKS_PER_COLUMN) },
    (_, index) => {
      const group = items.slice(
        index * RANKS_PER_COLUMN,
        (index + 1) * RANKS_PER_COLUMN
      );
      return {
        start: group[0]?.rank ?? 0,
        end: group.at(-1)?.rank ?? 0,
        items: group,
      };
    }
  );
}

function RankingRow({ industry }: { industry: RankingItem }) {
  return (
    <li>
      <span className="industry-ranking-number" aria-hidden="true">
        {String(industry.rank).padStart(2, '0')}
      </span>
      <div className="industry-ranking-body">
        <span className="industry-ranking-name">
          {industry.name}
          {industry.aiExcluded && (
            <span className="industry-ranking-flag">AI 제외 의견</span>
          )}
        </span>
        {(industry.reasons || (industry.checks?.length ?? 0) > 0) && (
          <details className="industry-ranking-detail">
            <summary>추천 이유 보기</summary>
            {industry.reasons && <p>{industry.reasons}</p>}
            {industry.checks && industry.checks.length > 0 && (
              <>
                <p className="industry-ranking-detail-label">입점 전 확인</p>
                <ul>
                  {industry.checks.map((check) => (
                    <li key={check}>{check}</li>
                  ))}
                </ul>
              </>
            )}
          </details>
        )}
      </div>
    </li>
  );
}

export default function IndustryRankingList({
  view,
  totalCount,
}: {
  view: RankingView;
  totalCount: number;
}) {
  const firstTen = view.items.slice(0, 10);
  const remaining = view.items.slice(10);
  return (
    <section className="industry-ranking" aria-label="업종 검토 순위">
      {view.notice && <p className="industry-ranking-notice">{view.notice}</p>}
      <div className="industry-ranking-mobile">
        <div className="industry-ranking-mobile-heading-row">
          <h3 className="industry-ranking-mobile-heading">먼저 검토할 업종</h3>
          <span className="industry-ranking-mobile-count">
            {totalCount}개 업종
          </span>
        </div>
        <ol className="industry-ranking-list" start={1}>
          {firstTen.map((industry) => (
            <RankingRow key={industry.rank} industry={industry} />
          ))}
        </ol>
        {remaining.length > 0 && (
          <details className="industry-ranking-more">
            <summary>나머지 업종 {remaining.length}개 보기</summary>
            <ol className="industry-ranking-list" start={11}>
              {remaining.map((industry) => (
                <RankingRow key={industry.rank} industry={industry} />
              ))}
            </ol>
          </details>
        )}
      </div>
      <div className="industry-ranking-groups">
        {rankGroups(view.items).map((group) => (
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
                <RankingRow key={industry.rank} industry={industry} />
              ))}
            </ol>
          </section>
        ))}
      </div>
      {view.groups.length > 0 && (
        <div className="industry-ranking-excluded">
          {view.groups.map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h3>{group.title}</h3>
              <p>{group.description}</p>
              <ul>
                {group.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
