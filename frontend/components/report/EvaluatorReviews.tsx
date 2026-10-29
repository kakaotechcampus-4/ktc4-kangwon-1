import Image from 'next/image';
import type { ReactNode } from 'react';
import { ArrowRight, ChevronDown } from 'lucide-react';
import { reportPalette as P } from '@/styles/reportPalette';
import { industryName } from '@/lib/api/industries';
import type { FactIndex } from '@/lib/api/segments';
import type {
  EvaluatorActor,
  EvaluatorReview,
  FactView,
  ReviewIssue,
  ReviewResolution,
} from '@/lib/api/types';

/**
 * 04 교차 검토 — 평가자 네 명이 "이 업종 추천을 따라도 되는지" 다시 판단한 결과.
 *
 * 백엔드의 지적 원문(comment·suggested_check)과 처리 이유(reason)는 "보고서 문장을
 * 이렇게 고쳐라"라는 AI 내부 검수 메모라서 본문에 쓰지 않는다. 대신 구조화된 값으로
 * 화면 문장을 만든다.
 *  - verdict → 결론 한 줄과 판정 분포
 *  - 지적의 kind·industry_code + 핵심어 → 쟁점(면적·설비 / 공사 / 손님 수요 / 임대 조건)
 *  - resolution.disposition → 반영 여부
 *  - space_requirements·space_fit·exclusive_area·existing_facilities fact → 읽히는 근거
 * 원문은 맨 아래 "원문 보기"에 접어 둔다.
 *
 * 확인할 조건은 02 핵심결론의 '입점 전 직접 확인'에 이미 반영돼 있어(처리 기록의
 * applied가 confirmation_conditions) 여기서는 반복하지 않고 그쪽으로 연결만 한다.
 *
 * 백엔드는 항상 네 자리를 채우고, 실패한 평가는 동의로 보지 않는다(docs/API_CONTRACT.md).
 * 쟁점 분류는 핵심어 기준이라, 백엔드가 지적별 카테고리와 평가자별 사용자용 요약을
 * 주게 되면 그 값으로 바꾼다.
 */

const ACTORS: Record<
  EvaluatorActor,
  { name: string; view: string; avatar: string }
> = {
  examiner: {
    name: '심사위원',
    view: '근거와 점수가 정확한가',
    avatar: '/images/review-avatars/examiner.svg',
  },
  founder: {
    name: '창업자',
    view: '실제로 운영할 수 있는가',
    avatar: '/images/review-avatars/founder.svg',
  },
  customer: {
    name: '고객',
    view: '손님이 찾아올 이유가 있는가',
    avatar: '/images/review-avatars/customer.svg',
  },
  landlord_advocate: {
    name: '임대인 대변인',
    view: '공실이 풀리고 오래 갈 수 있는가',
    avatar: '/images/review-avatars/landlord-advocate.svg',
  },
};
const ORDER: EvaluatorActor[] = [
  'examiner',
  'founder',
  'customer',
  'landlord_advocate',
];

type Verdict = 'agree' | 'conditional' | 'oppose' | 'failed';
const VERDICT: Record<
  Verdict,
  { label: string; color: string; bar: string; mark: string }
> = {
  agree: { label: '동의', color: P.brand, bar: '#2453D6', mark: '#D6E2FB' },
  conditional: {
    label: '조건부 동의',
    color: P.amber,
    bar: '#F0A43A',
    mark: '#FFE1A6',
  },
  oppose: { label: '반대', color: P.caution, bar: '#D9586C', mark: '#FBD3DA' },
  failed: {
    label: '검토 못 함',
    color: '#66758A',
    bar: '#C9D2DC',
    mark: '#E2E8EE',
  },
};
const VERDICT_ORDER: Verdict[] = ['agree', 'conditional', 'oppose', 'failed'];
const verdictOf = (r: EvaluatorReview): Verdict =>
  r.status === 'failed' || !r.verdict ? 'failed' : r.verdict;

// ── 쟁점 ────────────────────────────────────────────────────
type Theme = 'space' | 'buildout' | 'demand' | 'lease' | 'other';
const THEME_ORDER: Theme[] = ['space', 'buildout', 'demand', 'lease', 'other'];
const THEMES: Record<
  Theme,
  { title: string; stance: string; meaning: string; short: string }
> = {
  space: {
    title: '면적·설비가 업종에 맞는지',
    stance:
      '면적·설비 비교는 추정치라, 현장 확인 전에는 단정하기 어렵다고 봤어요.',
    meaning:
      '업종별 권장 면적과 필요한 설비는 일반적인 운영 규모를 추정한 값이에요. 맞지 않는다고 바로 안 되는 건 아니고, 현장에서 실제로 써 보는 확인이 필요해요.',
    short: '면적·설비 근거가 약하다는',
  },
  buildout: {
    title: '설비 공사를 누가, 얼마에 할지',
    stance:
      '설치할 수 있다는 것과 실제 공사는 다르니, 공사 범위와 비용부터 정해야 한다고 봤어요.',
    meaning:
      '"설치 가능"은 공사가 끝난 상태가 아니에요. 공사 범위와 비용을 누가 부담할지 먼저 정해야 해요.',
    short: '공사 조건이 정해지지 않았다는',
  },
  demand: {
    title: '손님이 실제로 있을지',
    stance:
      '후보 업종을 찾을 손님이 있는지 보여 주는 자료가 부족하다고 봤어요.',
    meaning:
      '이번 분석 자료로는 후보 업종의 손님 수요를 충분히 확인하지 못했어요. 점수가 높아도 수요는 따로 확인해야 해요.',
    short: '손님 수요 자료가 부족하다는',
  },
  lease: {
    title: '임대 조건과 수익',
    stance:
      '임대료·공실 기간·공사비 자료가 없어 임대 수익은 판단할 수 없다고 봤어요.',
    meaning:
      '이 리포트는 업종 적합도를 본 것이고, 임대 수익이나 임차인의 지급 능력은 판단하지 않았어요.',
    short: '임대 조건을 알 수 없다는',
  },
  other: {
    title: '근거가 부족한 판단',
    stance: '일부 판단의 근거가 약하다고 봤어요.',
    meaning: '근거가 약한 문장은 리포트에서 단정하지 않도록 고쳤어요.',
    short: '근거가 약하다는',
  },
};

function themeOf(issue: ReviewIssue): Theme {
  const text = issue.comment + issue.suggested_check;
  // 업종을 특정하지 않은 임대 조건 지적은 '수요'라는 말이 섞여도 임대 조건으로 본다.
  if (!issue.industry_code && /임대료|임대수익|임차|공실 기간/.test(text))
    return 'lease';
  if (/수요|손님/.test(text)) return 'demand';
  if (/공사|견적|반입|배치/.test(text) && issue.kind === 'action_condition')
    return 'buildout';
  if (/면적|환기|배기|급수|주방|설비|공간/.test(text)) return 'space';
  return 'other';
}

function mainTheme(review: EvaluatorReview): Theme {
  const count = new Map<Theme, number>();
  review.issues.forEach((issue) => {
    const theme = themeOf(issue);
    // 공사는 공간보다 구체적이라 같은 수면 공사를 대표로 쓴다
    count.set(
      theme,
      (count.get(theme) ?? 0) + (theme === 'buildout' ? 1.5 : 1)
    );
  });
  return [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'other';
}

// ── 근거 fact → 읽히는 값 ──────────────────────────────────────
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const FACILITY: [string, string][] = [
  ['kitchen', '주방'],
  ['ventilation', '배기'],
  ['water_supply', '급배수'],
];
const FACILITY_STATE: Record<string, string> = {
  present: '있음',
  installable: '설치 가능',
  unavailable: '설치 불가',
};

function areaRows(ids: string[], facts: FactIndex, all: FactView[]) {
  const area = all.find((f) => f.metric === 'exclusive_area')?.value;
  return ids
    .map((id) => facts.get(id))
    .filter(
      (f): f is FactView => f?.metric === 'space_requirements' && isObj(f.value)
    )
    .map((f) => {
      const value = f.value as Obj;
      const code = String(value.industry_code ?? f.industry_code ?? '');
      const fit = all.find(
        (x) => x.metric === 'space_fit' && x.industry_code === code
      )?.value;
      return {
        code,
        band: String(value.area_band ?? ''),
        mine: typeof area === 'string' ? area : '',
        fits: isObj(fit) ? fit.area === '일치' : null,
      };
    })
    .filter((row) => row.code && row.band);
}

function facilityLine(all: FactView[]): string | null {
  const value = all.find((f) => f.metric === 'existing_facilities')?.value;
  if (!isObj(value)) return null;
  const text = FACILITY.filter(
    ([key]) =>
      typeof value[key] === 'string' && FACILITY_STATE[value[key] as string]
  )
    .map(([key, name]) => `${name} ${FACILITY_STATE[value[key] as string]}`)
    .join(' · ');
  return text || null;
}

// 받침에 따라 은/는
function topic(name: string): string {
  const code = name.charCodeAt(name.length - 1) - 0xac00;
  return name + (code >= 0 && code % 28 !== 0 ? '은' : '는');
}

// 실패 이유는 임대인이 알아들을 수 있는 말로만 보여 준다.
function failureReason(code: string | null): string {
  if (code === 'BUDGET_EXCEEDED') return '분석 시간·비용 한도에 걸렸어요.';
  if (code === 'TIMEOUT') return '응답 시간이 초과됐어요.';
  if (code === 'REPORT_INVALID') return '검토 결과가 형식에 맞지 않았어요.';
  return '검토에 필요한 자료를 받지 못했어요.';
}

// ── 작은 조각 ────────────────────────────────────────────────
function Avatar({
  actor,
  size,
  ring,
  muted,
}: {
  actor: EvaluatorActor;
  size: number;
  ring?: string;
  muted?: boolean;
}) {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 overflow-hidden rounded-full bg-white"
      style={{
        width: size,
        height: size,
        boxShadow: ring ? `0 0 0 2.5px ${ring}` : undefined,
        filter: muted ? 'grayscale(1)' : undefined,
      }}
    >
      <Image
        src={ACTORS[actor].avatar}
        alt=""
        width={size}
        height={size}
        unoptimized
      />
    </span>
  );
}

function BlockLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-sm font-bold tracking-[0.02em] text-[#66758A]">
      {children}
    </h3>
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
    (a, b) => ORDER.indexOf(a.actor) - ORDER.indexOf(b.actor)
  );
  const allFacts = [...facts.values()];
  const resolutionOf = new Map(resolutions.map((r) => [r.issue_id, r]));
  const issues = ordered.flatMap((review) =>
    review.issues.map((issue) => ({
      actor: review.actor,
      issue,
      theme: themeOf(issue),
    }))
  );
  const reflected = issues.filter(
    ({ issue }) => resolutionOf.get(issue.issue_id)?.disposition === 'accepted'
  ).length;

  const counts = ordered.reduce(
    (acc, r) => ({ ...acc, [verdictOf(r)]: acc[verdictOf(r)] + 1 }),
    { agree: 0, conditional: 0, oppose: 0, failed: 0 } as Record<
      Verdict,
      number
    >
  );
  const done = ordered.length - counts.failed;

  if (done === 0) {
    // 네 명 모두 실패하면 빈 줄 네 개 대신 안내만 보인다.
    return (
      <div className="flex w-full flex-col gap-2 rounded-[24px] bg-[#EAF0F6] px-6 py-10 text-center">
        <p className="text-base font-semibold text-[#10233A]">
          이번 분석에서는 네 사람의 검토를 받지 못했어요.
        </p>
        <p className="text-sm leading-6 text-[#4B5866]">
          {failureReason(ordered[0]?.error_code ?? null)} 추천 결과는 확인된
          자료로 계산한 점수만으로 정리했고, 검토를 받지 못한 것을 동의로 보지
          않아요.
        </p>
      </div>
    );
  }

  // 결론: [앞, 강조할 말, 뒤] — 강조할 말은 임대인이 해야 할 판단 자체다.
  let headline: [string, string, string] = [
    `${done === ordered.length ? '네 명 모두' : `검토를 마친 ${done}명 모두`} 이 추천을 `,
    '그대로 따라도 된다',
    '고 봤어요',
  ];
  let tone: Verdict = 'agree';
  if (counts.oppose > 0 && counts.oppose * 2 >= done) {
    headline = ['이 추천을 ', '그대로 따르기 어렵다', '는 의견이 많아요'];
    tone = 'oppose';
  } else if (counts.conditional + counts.oppose > 0) {
    headline = [
      '추천 업종은 바로 정하기보다, ',
      '조건을 확인한 뒤 결정하라',
      '는 의견이 많아요',
    ];
    tone = 'conditional';
  }

  const parts: string[] = [];
  const supporters = counts.agree + counts.conditional;
  if (supporters)
    parts.push(
      `${supporters}명은 ${counts.conditional ? '몇 가지 조건을 확인하는 전제로 ' : ''}추천에 동의했고`
    );
  ordered
    .filter((r) => verdictOf(r) === 'oppose')
    .forEach((r) =>
      parts.push(
        `${topic(ACTORS[r.actor].name)} ${THEMES[mainTheme(r)].short} 이유로 반대했고`
      )
    );
  if (counts.failed)
    parts.push(`${counts.failed}명은 검토를 마치지 못해 동의로 보지 않았고`);
  const body = parts
    .join(', ')
    .replace(/했고$|았고$/, (m) => (m === '했고' ? '했어요' : '았어요'));
  const reflectedText = issues.length
    ? reflected === issues.length
      ? ` 지적 ${issues.length}건은 모두 이 리포트에 반영했어요.`
      : ` 지적 ${issues.length}건 중 ${reflected}건을 이 리포트에 반영했어요.`
    : '';

  const themes = THEME_ORDER.map((theme) => {
    const items = issues.filter((x) => x.theme === theme);
    return {
      theme,
      count: items.length,
      actors: [...new Set(items.map((x) => x.actor))],
      industries: [
        ...new Set(
          items
            .map((x) => x.issue.industry_code)
            .filter((c): c is string => Boolean(c))
        ),
      ],
      factIds: [...new Set(items.flatMap((x) => x.issue.fact_ids))],
      allReflected: items.every(
        (x) => resolutionOf.get(x.issue.issue_id)?.disposition === 'accepted'
      ),
    };
  }).filter((t) => t.count > 0);
  const facility = facilityLine(allFacts);
  const mark = VERDICT[tone].mark;

  return (
    <div className="flex w-full flex-col">
      {/* ① 결론 + 판정 분포 */}
      <section className="grid gap-10 lg:grid-cols-[1fr_370px] lg:items-center lg:gap-14">
        <div className="flex flex-col gap-5">
          <div>
            <span
              aria-hidden
              className="block h-10 font-serif text-[72px] leading-none font-black sm:h-12 sm:text-[88px]"
              style={{ color: VERDICT[tone].bar }}
            >
              &ldquo;
            </span>
            <p className="break-keep text-[28px] leading-[1.35] font-extrabold tracking-[-0.03em] text-[#10233A] sm:text-[34px]">
              {headline[0]}
              <span
                style={{
                  backgroundImage: `linear-gradient(transparent 58%, ${mark} 58%, ${mark} 92%, transparent 92%)`,
                  boxDecorationBreak: 'clone',
                  WebkitBoxDecorationBreak: 'clone',
                  padding: '0 2px',
                }}
              >
                {headline[1]}
              </span>
              {headline[2]}
            </p>
          </div>
          <p className="text-sm font-semibold text-[#8A97A5]">
            네 평가자가 각자 입장에서 &ldquo;이 업종 추천을 따라도 되는지&rdquo;
            다시 판단한 결과예요.
          </p>
          <p className="break-keep text-lg leading-8 text-[#4B5866]">
            {body}.{reflectedText}
          </p>
          {/* 확인할 것은 핵심결론 한 곳에서만 보여 준다 */}
          <a
            href="#conclusion"
            className="group mt-1 flex w-fit items-center gap-2 rounded-full border bg-white py-2.5 pr-4 pl-5 text-[15px] font-semibold text-[#10233A] transition-colors hover:border-[#2453D6] hover:text-[#2453D6]"
            style={{ borderColor: P.line }}
          >
            <span className="hidden sm:inline">
              확인할 조건은 &lsquo;입점 전 직접 확인&rsquo;에 정리했어요
            </span>
            <span className="sm:hidden">
              &lsquo;입점 전 직접 확인&rsquo; 보기
            </span>
            <ArrowRight
              size={18}
              className="transition-transform group-hover:translate-x-0.5"
              aria-hidden
            />
          </a>
        </div>

        <div className="flex flex-col gap-4" aria-label="평가자별 판정">
          <div className="flex h-3 gap-1" aria-hidden>
            {ordered.map((r) => (
              <span
                key={r.actor}
                className="flex-1 first:rounded-l-full last:rounded-r-full"
                style={{ backgroundColor: VERDICT[verdictOf(r)].bar }}
              />
            ))}
          </div>
          <ul className="grid grid-cols-4 gap-2">
            {ordered.map((r) => {
              const v = verdictOf(r);
              return (
                <li
                  key={r.actor}
                  className="flex flex-col items-center gap-1.5 text-center"
                >
                  <Avatar
                    actor={r.actor}
                    size={52}
                    ring={VERDICT[v].bar}
                    muted={v === 'failed'}
                  />
                  <span className="mt-1 text-[13px] font-bold whitespace-nowrap text-[#10233A] sm:text-sm">
                    {ACTORS[r.actor].name}
                  </span>
                  <span
                    className="text-xs font-semibold whitespace-nowrap sm:text-[13px]"
                    style={{ color: VERDICT[v].color }}
                  >
                    {VERDICT[v].label}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="text-center text-sm text-[#66758A]">
            {VERDICT_ORDER.filter((v) => counts[v])
              .map((v) => `${VERDICT[v].label} ${counts[v]}`)
              .join(' · ')}
          </p>
        </div>
      </section>

      {/* ② 네 사람의 의견 — 테두리·그림자 없이 옅은 바탕 면으로만 묶는다 */}
      <section className="mt-14 flex flex-col gap-2 rounded-[24px] bg-[#EAF0F6] px-5 pt-6 pb-2 sm:px-8 sm:pt-7">
        <BlockLabel>네 사람의 의견</BlockLabel>
        <ul className="divide-y divide-[#D5DEE7]">
          {ordered.map((r) => {
            const v = verdictOf(r);
            const opinion =
              v === 'failed'
                ? `이번에는 검토를 마치지 못했어요. ${failureReason(r.error_code)} 동의로 보지 않아요.`
                : r.issues.length
                  ? THEMES[mainTheme(r)].stance
                  : '따로 지적한 점이 없어요.';
            return (
              <li
                key={r.actor}
                className="grid grid-cols-[40px_1fr] gap-x-4 gap-y-1.5 py-5 sm:grid-cols-[40px_170px_1fr_auto] sm:items-center sm:gap-x-6"
              >
                <Avatar actor={r.actor} size={40} muted={v === 'failed'} />
                <div className="flex items-center justify-between gap-3 sm:block">
                  <div>
                    <p className="text-base font-bold text-[#10233A]">
                      {ACTORS[r.actor].name}
                    </p>
                    <p className="text-[13px] text-[#8A97A5]">
                      {ACTORS[r.actor].view}
                    </p>
                  </div>
                  <span
                    className="text-sm font-bold sm:hidden"
                    style={{ color: VERDICT[v].color }}
                  >
                    {VERDICT[v].label}
                  </span>
                </div>
                <p className="col-start-2 break-keep text-[15px] leading-7 text-[#3D4A5C] sm:col-start-auto">
                  {opinion}
                </p>
                <span
                  className="hidden text-sm font-bold whitespace-nowrap sm:block"
                  style={{ color: VERDICT[v].color }}
                >
                  {VERDICT[v].label}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ③ 평가자들이 짚은 점 — 근거가 필요한 사람만 읽는 층 */}
      {themes.length > 0 && (
        <section className="mt-14 flex flex-col gap-4">
          <BlockLabel>평가자들이 짚은 점</BlockLabel>
          <ol className="border-t" style={{ borderColor: P.line }}>
            {themes.map((t) => {
              const meta = THEMES[t.theme];
              const areas =
                t.theme === 'space' ? areaRows(t.factIds, facts, allFacts) : [];
              return (
                <li
                  key={t.theme}
                  className="grid gap-3 border-b py-6 sm:grid-cols-[220px_1fr] sm:gap-8"
                  style={{ borderColor: P.line }}
                >
                  <div className="flex flex-col gap-2">
                    <p className="text-base font-bold text-[#10233A]">
                      {meta.title}
                    </p>
                    <span className="flex items-center gap-1.5">
                      <span className="flex -space-x-1.5">
                        {t.actors.map((a) => (
                          <Avatar key={a} actor={a} size={20} ring="#F5F8FB" />
                        ))}
                      </span>
                      <span className="text-[13px] text-[#8A97A5]">
                        {t.actors.map((a) => ACTORS[a].name).join(' · ')}
                      </span>
                    </span>
                  </div>
                  <div className="flex flex-col gap-3">
                    <p className="break-keep text-[15px] leading-7 text-[#3D4A5C]">
                      {meta.meaning}
                    </p>
                    {areas.length > 0 && (
                      <table className="w-full max-w-[460px] text-sm">
                        <caption className="pb-1.5 text-left text-[13px] text-[#8A97A5]">
                          업종별 권장 면적
                          {areas[0].mine
                            ? ` · 이 상가 ${areas[0].mine}`
                            : ''}{' '}
                          (추정치, 법적 기준 아님)
                        </caption>
                        <tbody>
                          {areas.map((a) => (
                            <tr
                              key={a.code}
                              className="border-t"
                              style={{ borderColor: P.line }}
                            >
                              <td className="py-1.5 text-[#3D4A5C]">
                                {industryName(a.code)}
                              </td>
                              <td className="py-1.5 text-right tabular-nums text-[#4B5866]">
                                {a.band}
                              </td>
                              <td
                                className="w-16 py-1.5 text-right text-[13px] font-bold"
                                style={{
                                  color:
                                    a.fits === null
                                      ? '#8A97A5'
                                      : a.fits
                                        ? P.brand
                                        : P.amber,
                                }}
                              >
                                {a.fits === null
                                  ? '확인 필요'
                                  : a.fits
                                    ? '범위 안'
                                    : '범위 밖'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {t.theme === 'buildout' && facility && (
                      <p className="text-sm text-[#4B5866]">
                        입력하신 설비: {facility}
                      </p>
                    )}
                    <p className="text-[13px] text-[#8A97A5]">
                      {t.industries.length
                        ? t.industries.map(industryName).join(' · ')
                        : '추천 결과 전체'}
                      {' · '}
                      {t.allReflected ? '리포트에 반영됨' : '일부 반영'}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {/* ④ 원문 — 투명성을 위해 남기되 글자 링크 수준으로 접어 둔다 */}
      {issues.length > 0 && (
        <details className="group mt-8">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-sm font-semibold text-[#66758A] [&::-webkit-details-marker]:hidden">
            AI 평가자가 남긴 원문 {issues.length}건 보기
            <ChevronDown
              size={16}
              className="transition-transform group-open:rotate-180"
              aria-hidden
            />
          </summary>
          <ul className="mt-4 flex flex-col gap-4">
            {issues.map(({ actor, issue }) => (
              <li key={issue.issue_id} className="flex gap-3">
                <Avatar actor={actor} size={24} />
                <p className="min-w-0 flex-1 break-keep text-sm leading-6 text-[#4B5866]">
                  <span className="text-[#8A97A5]">
                    {ACTORS[actor].name} ·{' '}
                    {issue.industry_code
                      ? industryName(issue.industry_code)
                      : '전체'}
                    {' — '}
                  </span>
                  {issue.comment}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}

      {limitations && (
        <p className="mt-10 rounded-2xl bg-white px-6 py-5 text-sm leading-6 text-[#4B5866]">
          <strong className="text-[#10233A]">분석의 한계 · </strong>
          {limitations}
        </p>
      )}
    </div>
  );
}
