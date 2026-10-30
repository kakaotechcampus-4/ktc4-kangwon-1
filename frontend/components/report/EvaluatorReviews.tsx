'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Check, CircleMinus, CircleHelp, X } from 'lucide-react';
import Image from 'next/image';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import { industryName } from '@/lib/api/industries';
import type { FactIndex } from '@/lib/api/segments';
import type {
  EvaluatorActor,
  EvaluatorReview,
  FactSource,
  FactView,
  ReviewIssue,
  ReviewResolution,
} from '@/lib/api/types';

/**
 * 평가자 네 명의 검토. 백엔드는 항상 네 자리를 채우고, 실패한 평가는
 * 동의로 보지 않는다(docs/API_CONTRACT.md) — 그래서 실패도 숨기지 않고 표시한다.
 *
 * 카드의 대표 문장은 평가자별 요약 필드가 아직 없어 첫 번째 지적의 comment를 쓴다.
 * 백엔드와 요약 필드를 합의하면 그 값으로 바꾼다.
 */
const ACTOR_LABELS: Record<
  EvaluatorActor,
  { name: string; view: string; avatar: string }
> = {
  examiner: {
    name: '심사위원',
    view: '근거와 점수의 정확성',
    avatar: '/images/review-avatars/examiner.svg',
  },
  founder: {
    name: '창업자',
    view: '공간과 실제 운영 가능성',
    avatar: '/images/review-avatars/founder.svg',
  },
  customer: {
    name: '고객',
    view: '방문 동기와 고객층의 적합성',
    avatar: '/images/review-avatars/customer.svg',
  },
  landlord_advocate: {
    name: '임대인 대변인',
    view: '공실 해소와 임대 지속성',
    avatar: '/images/review-avatars/landlord-advocate.svg',
  },
};

const ACTOR_ORDER: EvaluatorActor[] = [
  'examiner',
  'founder',
  'customer',
  'landlord_advocate',
];

const VERDICT_LABELS = {
  agree: {
    label: '동의',
    meaning: '추천 결과를 그대로 믿어도 된다고 봤어요',
    color: reportPalette.navy,
    wash: reportPalette.blueWash,
  },
  conditional: {
    label: '조건부 동의',
    meaning: '아래 내용을 확인하면 추천을 따라도 된다고 봤어요',
    color: reportPalette.amber,
    wash: reportPalette.amberWash,
  },
  oppose: {
    label: '반대',
    meaning: '추천 결과를 그대로 따르기 어렵다고 봤어요',
    color: reportPalette.caution,
    wash: reportPalette.rose,
  },
} as const;

const DISPOSITION_LABELS = {
  accepted: {
    label: '지적 반영',
    Icon: Check,
    color: reportPalette.navy,
    wash: reportPalette.blueWash,
  },
  partial: {
    label: '일부 반영',
    Icon: CircleMinus,
    color: reportPalette.amber,
    wash: reportPalette.amberWash,
  },
  rejected: {
    label: '반영하지 않음',
    Icon: X,
    color: reportPalette.caution,
    wash: reportPalette.rose,
  },
} as const;

const SOURCE_LABELS: Record<FactSource, string> = {
  floating_population: '유동인구',
  resident_population: '거주인구',
  worker_population: '직장인구',
  commercial_area: '상권 분석',
  business_lifecycle: '개폐업',
  map: '지도',
  regulation: '규제',
  user: '입력 정보',
  baseline: '서울 기준선',
  industry_profile: '업종 기준',
};

// 실패 이유는 임대인이 알아들을 수 있는 말로만 보여 준다.
function failureReason(code: string | null): string {
  if (code === 'BUDGET_EXCEEDED') return '분석 시간·비용 한도에 걸렸어요.';
  if (code === 'TIMEOUT') return '응답 시간이 초과됐어요.';
  if (code === 'REPORT_INVALID') return '검토 결과가 형식에 맞지 않았어요.';
  return '검토에 필요한 자료를 받지 못했어요.';
}

function scopeLabel(issue: ReviewIssue | undefined): string {
  return issue?.industry_code
    ? `${industryName(issue.industry_code)} 검토`
    : '추천 결과 전체 검토';
}

// 근거 카드에 쓰는 지표 이름. 목록에 없으면 출처 이름으로 대신한다.
const METRIC_LABELS: Record<string, string> = {
  radius_m: '분석 반경',
  baseline_radius_m: '비교 기준 반경',
  distance_m: '거리',
  density_per_km2: '점포 밀도(㎢당)',
  competition_index: '경쟁 지수',
  seoul_median_density: '서울 중위 밀도',
  lq: '입지계수',
  store_count: '점포 수',
  opening_count: '개업 수',
  closing_count: '폐업 수',
  recent_year_close_rate: '최근 1년 폐업률',
  turnover_rate: '회전율',
  net_change_rate: '순증감률',
  yoy_change: '전년 대비 변화',
  age_share: '연령 비중',
  weekend_index: '주말 지수',
  floor: '층',
  exclusive_area: '전용 면적',
};

function factValue(fact: FactView): string {
  const { value, unit } = fact;
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (unit === '비율') return `${(value * 100).toFixed(1)}%`;
    const suffix = unit === '배수' ? '배' : unit;
    return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}${suffix}`;
  }
  if (typeof value === 'string') return value;
  return '원문 확인 필요';
}

/** 인용 근거: 지표 이름과 값을 크게, 출처·기간은 아래에 한 번만 */
function Evidence({ ids, facts }: { ids: string[]; facts: FactIndex }) {
  const unique = [...new Set(ids)];
  const found = unique
    .map((id) => facts.get(id))
    .filter((fact): fact is FactView => Boolean(fact));
  const missing = unique.length - found.length;
  if (unique.length === 0) return null;
  const captions = [
    ...new Set(
      found.map(
        (fact) =>
          `${SOURCE_LABELS[fact.source] ?? fact.source} 자료${fact.period ? ` · ${fact.period}` : ''}`
      )
    ),
  ];
  return (
    <DetailBlock title="인용 근거">
      {found.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
          {found.map((fact) => (
            <div key={fact.fact_id} className="flex min-w-0 flex-col gap-1">
              <dt className="text-sm" style={{ color: colors.text.tertiary }}>
                {METRIC_LABELS[fact.metric] ??
                  SOURCE_LABELS[fact.source] ??
                  fact.metric}
                {fact.industry_code
                  ? ` · ${industryName(fact.industry_code)}`
                  : ''}
              </dt>
              <dd
                className="break-words text-xl font-bold"
                style={{ color: reportPalette.ink }}
              >
                {factValue(fact)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="text-xs leading-5" style={{ color: colors.text.tertiary }}>
        {[
          ...captions,
          ...(missing > 0 ? [`불러오지 못한 근거 ${missing}건`] : []),
        ].join(' · ')}
      </p>
    </DetailBlock>
  );
}

function DetailBlock({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm" style={{ color: colors.text.tertiary }}>
        {title}
      </p>
      {children}
    </div>
  );
}

function ResolutionBadge({
  resolution,
}: {
  resolution: ReviewResolution | undefined;
}) {
  const meta = resolution ? DISPOSITION_LABELS[resolution.disposition] : null;
  const Icon = meta?.Icon ?? CircleHelp;
  return (
    <span
      className="inline-flex items-center gap-1.5 text-sm font-semibold"
      style={{ color: meta?.color ?? colors.text.tertiary }}
    >
      <Icon size={16} strokeWidth={2.2} aria-hidden />
      {meta?.label ?? '처리 기록 없음'}
    </span>
  );
}

/** 대표 지적의 처리 결과 요약 상자. 무엇을 바꿨는지(applied)를 먼저 보인다. */
function ResolutionSummary({
  resolution,
}: {
  resolution: ReviewResolution | undefined;
}) {
  const text = resolution
    ? resolution.applied.length
      ? resolution.applied.join(' · ')
      : resolution.reason
    : '최종 판단에서 이 지적을 어떻게 처리했는지 기록이 남지 않았어요.';
  return (
    <div
      className="flex flex-col gap-2 rounded-2xl px-5 py-4"
      style={{ backgroundColor: reportPalette.canvas }}
    >
      <ResolutionBadge resolution={resolution} />
      <p className="text-sm leading-6" style={{ color: colors.text.secondary }}>
        {text}
      </p>
    </div>
  );
}

/** 펼쳤을 때 보이는 지적 하나의 상세: 처리 이유 → 인용 근거 → 남은 확인 */
function IssueDetail({
  issue,
  resolution,
  facts,
  showHeading,
}: {
  issue: ReviewIssue;
  resolution: ReviewResolution | undefined;
  facts: FactIndex;
  showHeading: boolean;
}) {
  const remaining = [
    ...new Set([
      ...(resolution?.not_applied ?? []),
      ...(issue.suggested_check ? [issue.suggested_check] : []),
    ]),
  ];
  return (
    <li className="flex flex-col gap-5">
      {showHeading && (
        <div className="flex flex-col gap-2">
          <p className="text-sm" style={{ color: colors.text.tertiary }}>
            {scopeLabel(issue)}
          </p>
          <p
            className="break-keep text-[15px] font-semibold leading-7"
            style={{ color: reportPalette.ink }}
          >
            {issue.comment}
          </p>
          <ResolutionBadge resolution={resolution} />
        </div>
      )}
      <DetailBlock title="처리 이유">
        <p
          className="text-base leading-7"
          style={{ color: colors.text.primary }}
        >
          {resolution?.reason ?? '처리 기록이 남지 않았어요.'}
        </p>
      </DetailBlock>
      <Evidence
        ids={[...issue.fact_ids, ...(resolution?.fact_ids ?? [])]}
        facts={facts}
      />
      {remaining.length > 0 && (
        <DetailBlock title="남은 확인">
          {remaining.map((text) => (
            <p
              key={text}
              className="text-base leading-7"
              style={{ color: colors.text.primary }}
            >
              {text}
            </p>
          ))}
        </DetailBlock>
      )}
    </li>
  );
}

function ReviewerCard({
  review,
  resolutions,
  facts,
}: {
  review: EvaluatorReview;
  resolutions: ReadonlyMap<string, ReviewResolution>;
  facts: FactIndex;
}) {
  const actor = ACTOR_LABELS[review.actor];
  const failed = review.status === 'failed';
  const verdict =
    !failed && review.verdict ? VERDICT_LABELS[review.verdict] : null;
  const lead = review.issues[0];
  const leadResolution = lead ? resolutions.get(lead.issue_id) : undefined;
  // 대표 문장은 3줄로 자르고, "더 보기"나 펼침 영역을 열면 전체를 보인다.
  const [expanded, setExpanded] = useState(false);
  const [clamped, setClamped] = useState(false);
  const leadRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const node = leadRef.current;
    if (!node || expanded) return;
    const measure = () => setClamped(node.scrollHeight > node.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [expanded, lead?.comment]);

  return (
    <li
      className="flex flex-col overflow-hidden rounded-[28px] border bg-white"
      style={{
        borderColor: reportPalette.line,
        opacity: failed ? 0.75 : 1,
      }}
    >
      <div className="flex flex-1 flex-col gap-6 p-6 sm:p-8">
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full"
            style={{
              filter: failed ? 'grayscale(1)' : undefined,
            }}
          >
            <Image
              src={actor.avatar}
              alt=""
              width={48}
              height={48}
              unoptimized
              className="h-12 w-12 object-cover"
            />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <p
                className="text-lg font-bold"
                style={{ color: reportPalette.ink }}
              >
                {actor.name}
              </p>
              <span
                className="shrink-0 rounded-lg px-2.5 py-1 text-sm font-semibold"
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
            <p
              className="mt-0.5 text-sm"
              style={{ color: colors.text.tertiary }}
            >
              {actor.view}
            </p>
          </div>
        </div>

        {failed ? (
          <div className="flex flex-col gap-1">
            <p
              className="text-base font-semibold"
              style={{ color: colors.text.secondary }}
            >
              이번에는 검토를 마치지 못했어요.
            </p>
            <p
              className="text-sm leading-6"
              style={{ color: colors.text.tertiary }}
            >
              {failureReason(review.error_code)} 검토하지 못한 의견은 동의로
              보지 않아요.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <p className="text-sm" style={{ color: colors.text.tertiary }}>
                {scopeLabel(lead)}
              </p>
              {lead ? (
                // 잘렸을 때는 마지막 줄 오른쪽 끝에 "더 보기"를 겹쳐 두고,
                // 펼쳤을 때는 문장 끝에 "접기"를 이어 붙인다.
                <div className="relative">
                  <p
                    ref={leadRef}
                    className={`break-keep text-base font-semibold leading-7 ${
                      expanded ? '' : 'line-clamp-3'
                    }`}
                    style={{ color: reportPalette.ink }}
                  >
                    {lead.comment}
                    {expanded && (
                      <button
                        type="button"
                        onClick={() => setExpanded(false)}
                        className="ml-2 text-sm font-medium underline-offset-4 hover:underline"
                        style={{ color: colors.text.tertiary }}
                      >
                        접기
                      </button>
                    )}
                  </p>
                  {clamped && !expanded && (
                    <button
                      type="button"
                      onClick={() => setExpanded(true)}
                      className="absolute bottom-0 right-0 bg-linear-to-r from-transparent via-white via-30% to-white pl-10 text-sm font-medium leading-7 underline-offset-4 hover:underline"
                      style={{ color: colors.text.tertiary }}
                    >
                      … 더 보기
                    </button>
                  )}
                </div>
              ) : (
                // 평가자가 남긴 말이 없으므로 따옴표나 굵은 인용처럼 보이지 않게 한다.
                <p
                  className="text-base leading-7"
                  style={{ color: colors.text.secondary }}
                >
                  {actor.view} 관점에서 따로 지적한 점이 없어요.
                </p>
              )}
            </div>
            {lead && <ResolutionSummary resolution={leadResolution} />}
          </>
        )}
      </div>

      {!failed && review.issues.length > 0 && (
        <details
          className="group border-t"
          style={{ borderColor: reportPalette.line }}
          onToggle={(event) => {
            if (event.currentTarget.open) setExpanded(true);
          }}
        >
          <summary
            className="flex cursor-pointer list-none items-center gap-2 px-6 py-5 text-base font-medium sm:px-8 [&::-webkit-details-marker]:hidden"
            style={{ color: reportPalette.navy }}
          >
            <span
              aria-hidden
              className="text-xs transition-transform group-open:rotate-90"
            >
              ▶
            </span>
            {review.issues.length > 1
              ? `지적 ${review.issues.length}개와 처리 결과 모두 보기`
              : '처리 이유와 근거 보기'}
          </summary>
          <ul
            className="flex flex-col gap-8 divide-y px-6 pb-8 sm:px-8 [&>li+li]:pt-8"
            style={{ borderColor: reportPalette.line }}
          >
            {review.issues.map((issue, index) => (
              <IssueDetail
                key={issue.issue_id}
                issue={issue}
                resolution={resolutions.get(issue.issue_id)}
                facts={facts}
                showHeading={index > 0}
              />
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

export default function EvaluatorReviews({
  reviews,
  resolutions,
  facts,
  limitations,
}: {
  reviews: EvaluatorReview[];
  resolutions: ReviewResolution[];
  facts: FactIndex;
  limitations?: string;
}) {
  const ordered = [...reviews].sort(
    (a, b) => ACTOR_ORDER.indexOf(a.actor) - ACTOR_ORDER.indexOf(b.actor)
  );
  const completed = ordered.filter((r) => r.status === 'completed').length;
  const resolutionIndex = new Map(resolutions.map((r) => [r.issue_id, r]));

  return (
    <div className="flex w-full flex-col gap-5">
      {/* 판정은 업종 하나가 아니라 AI 추천 판단 전체에 대한 것이라 먼저 밝혀 둔다. */}
      <div
        className="flex flex-col gap-5 border-y py-7"
        style={{ borderColor: reportPalette.line }}
      >
        <p className="text-sm" style={{ color: colors.text.secondary }}>
          배지는 추천 판단에 대한 각 평가자의 의견이에요.
        </p>
        <dl className="grid sm:grid-cols-3">
          {Object.values(VERDICT_LABELS).map((verdict, index) => (
            <div
              key={verdict.label}
              className={`flex flex-col items-start gap-2.5 py-4 first:pt-0 last:pb-0 sm:py-1 sm:first:pt-1 sm:last:pb-1 ${
                index > 0 ? 'border-t sm:border-l sm:border-t-0 sm:pl-8' : ''
              } ${index < 2 ? 'sm:pr-8' : ''}`}
              style={{ borderColor: reportPalette.line }}
            >
              <dt
                className="rounded-md px-2 py-0.5 text-sm font-semibold"
                style={{ color: verdict.color, backgroundColor: verdict.wash }}
              >
                {verdict.label}
              </dt>
              <dd
                className="text-sm leading-6"
                style={{ color: colors.text.secondary }}
              >
                {verdict.meaning}
              </dd>
            </div>
          ))}
        </dl>
        {completed < ordered.length && (
          <p
            className="text-sm leading-6"
            style={{ color: colors.text.tertiary }}
          >
            <strong>검토 못 함</strong>은 검토를 마치지 못했다는 뜻이며, 동의로
            보지 않아요.
          </p>
        )}
      </div>

      {completed === 0 ? (
        // 네 명 모두 실패하면 빈 카드 네 장 대신 안내 한 줄만 보인다.
        <div
          className="rounded-[28px] border bg-white px-6 py-10 text-center"
          style={{ borderColor: reportPalette.line }}
        >
          <p
            className="text-base font-semibold"
            style={{ color: reportPalette.ink }}
          >
            이번 분석에서는 네 사람의 검토를 받지 못했어요.
          </p>
          <p
            className="mt-2 text-sm leading-6"
            style={{ color: colors.text.secondary }}
          >
            {failureReason(ordered[0]?.error_code ?? null)} 추천 결과는 확인된
            자료로 계산한 점수만으로 정리했고, 검토를 받지 못한 것을 동의로 보지
            않아요.
          </p>
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 md:gap-5">
          {ordered.map((review) => (
            <ReviewerCard
              key={review.actor}
              review={review}
              resolutions={resolutionIndex}
              facts={facts}
            />
          ))}
        </ul>
      )}

      {limitations && (
        <p
          className="rounded-2xl bg-white px-6 py-5 text-sm leading-6"
          style={{ color: colors.text.secondary }}
        >
          <strong style={{ color: reportPalette.ink }}>분석의 한계 · </strong>
          {limitations}
        </p>
      )}
    </div>
  );
}
