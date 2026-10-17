import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import { industryName } from '@/lib/api/industries';
import type { EvaluatorActor, EvaluatorReview } from '@/lib/api/types';

/**
 * 평가자 네 명의 검토 상태. 백엔드는 항상 네 자리를 채우고, 실패한 평가는
 * 동의로 보지 않는다(docs/API_CONTRACT.md) — 그래서 실패도 숨기지 않고 표시한다.
 */

const ACTOR_LABELS: Record<EvaluatorActor, { name: string; view: string }> = {
  examiner: { name: '심사위원', view: '근거와 점수가 맞는지' },
  founder: { name: '창업자', view: '실제로 장사가 될지' },
  customer: { name: '고객', view: '찾아올 이유가 있는지' },
  landlord_advocate: { name: '임대인 대변인', view: '임대인에게 유리한지' },
};

const VERDICT_LABELS = {
  agree: {
    label: '동의',
    color: reportPalette.navy,
    wash: reportPalette.blueWash,
  },
  conditional: {
    label: '조건부 동의',
    color: reportPalette.amber,
    wash: reportPalette.amberWash,
  },
  oppose: {
    label: '반대',
    color: reportPalette.caution,
    wash: reportPalette.rose,
  },
} as const;

export default function EvaluatorReviews({
  reviews,
  completeness,
  limitations,
}: {
  reviews: EvaluatorReview[];
  completeness: number;
  limitations?: string;
}) {
  const completed = Math.round(completeness * reviews.length);

  return (
    <section
      className="mt-8 w-full rounded-xl border bg-white"
      style={{ borderColor: reportPalette.line }}
    >
      <header
        className="flex flex-wrap items-baseline justify-between gap-2 border-b px-6 py-4"
        style={{ borderColor: reportPalette.line }}
      >
        <div>
          <h3
            className="text-lg font-bold"
            style={{ color: reportPalette.ink }}
          >
            평가자 네 명의 검토
          </h3>
          <p className="mt-1 text-sm" style={{ color: colors.text.secondary }}>
            서로 다른 입장의 평가자가 AI 판단을 검토하고, 지적은 최종 결과에
            반영했습니다.
          </p>
        </div>
        <span className="text-sm font-semibold">
          {completed} / {reviews.length}명 검토 완료
        </span>
      </header>
      <ul className="grid gap-4 px-6 py-5 sm:grid-cols-2">
        {reviews.map((review) => {
          const actor = ACTOR_LABELS[review.actor];
          const verdict =
            review.status === 'completed' && review.verdict
              ? VERDICT_LABELS[review.verdict]
              : null;
          return (
            <li
              key={review.actor}
              className="flex flex-col gap-3 rounded-xl p-4"
              style={{ backgroundColor: reportPalette.canvas }}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-bold">{actor.name}</p>
                  <p
                    className="text-sm"
                    style={{ color: colors.text.tertiary }}
                  >
                    {actor.view}
                  </p>
                </div>
                <span
                  className="shrink-0 rounded-md px-2.5 py-1 text-sm font-semibold"
                  style={
                    verdict
                      ? { color: verdict.color, backgroundColor: verdict.wash }
                      : {
                          color: colors.text.secondary,
                          backgroundColor: colors.neutral.border,
                        }
                  }
                >
                  {verdict?.label ?? '검토 못 함'}
                </span>
              </div>
              {review.issues.length > 0 && (
                <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-6">
                  {review.issues.map((issue) => (
                    <li key={issue.issue_id}>
                      {issue.industry_code && (
                        <strong>{industryName(issue.industry_code)}: </strong>
                      )}
                      {issue.comment}
                    </li>
                  ))}
                </ul>
              )}
              {review.status === 'failed' && (
                <p className="text-sm" style={{ color: colors.text.secondary }}>
                  이 평가자의 검토를 마치지 못해 동의로 보지 않습니다.
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {limitations && (
        <p
          className="border-t px-6 py-4 text-sm leading-6"
          style={{
            borderColor: reportPalette.line,
            color: colors.text.secondary,
          }}
        >
          <strong>분석의 한계 · </strong>
          {limitations}
        </p>
      )}
    </section>
  );
}
