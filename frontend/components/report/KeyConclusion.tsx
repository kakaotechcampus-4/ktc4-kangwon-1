'use client';

import type { ReactNode } from 'react';
import { Building2, TriangleAlert } from 'lucide-react';
import { reportPalette as P } from '@/styles/reportPalette';
import type { FactIndex } from '@/lib/api/segments';
import type { FactView } from '@/lib/api/types';

/**
 * 02 핵심 결론.
 *
 * - 1행: 가장 먼저 검토할 업종 | 검토 방향 (카드·구분선 없이 같은 행)
 * - 입점 전 확인할 N가지: 이 장의 중심. 결론 패널의 "N가지"에서 점선으로 이어진다. 후보의 위험·확인 조건 문장을 쟁점별로
 *   묶고, fact로 읽히는 근거를 붙이고, 번호 순서대로 읽게 한다.
 *
 * 백엔드 문장(risks·confirmation_conditions)에는 "점수표·신뢰도·법규 적합성" 같은
 * 내부 표현이 섞여 있어, 원문은 보여 주지 않고 화면 문장은 쟁점별 고정 문구로
 * 만든다. 쟁점 분류는 핵심어 기준이라, 백엔드가 조건별 카테고리를
 * 주게 되면 그 값으로 바꾼다.
 */

type Topic =
  'area' | 'facility' | 'access' | 'use' | 'regulation' | 'demand' | 'other';

const TOPICS: Record<
  Exclude<Topic, 'other'>,
  { title: string; test: RegExp; how: string }
> = {
  area: {
    title: '실제로 쓸 수 있는 면적',
    test: /면적|구획|실측/,
    how: '도면과 현장 실측으로 기둥·복도를 뺀 사용 면적을 재고, 업종에 맞게 나눠 쓸 수 있는지 확인하세요.',
  },
  facility: {
    title: '주방·환기·급배수 설비',
    test: /환기|배기|급수|급배수|주방|설비|전력/,
    how: '이 업종에 필요한 설비를 지금 쓸 수 있는지, 없다면 설치 위치와 비용을 설비 업체에 확인하세요.',
  },
  access: {
    title: '드나들기 쉬운지와 간판 노출',
    test: /엘리베이터|동선|간판|노출|접근/,
    how: '손님이 입구와 엘리베이터를 쉽게 찾을 수 있는지, 간판을 어디에 달 수 있는지 현장에서 확인하세요.',
  },
  use: {
    title: '건축물 용도와 인허가',
    test: /용도|인허가|허가/,
    how: '건축물대장에서 용도를 확인하고, 이 업종으로 영업 신고·인허가가 되는지 관할 구청에 문의하세요.',
  },
  regulation: {
    title: '입점 규제',
    test: /보호구역|규제|제한/,
    how: '학교 주변 보호구역 등으로 이 업종의 영업이 제한되지 않는지 관할 구청이나 교육지원청에 확인하세요.',
  },
  demand: {
    title: '이 업종을 찾을 손님',
    test: /수요|고객|매출|손님/,
    how: '주변에 이 업종을 이용할 사람이 실제로 있는지 현장을 둘러보고, 인근 중개사에게 비슷한 업종의 임차 문의가 있었는지 물어보세요.',
  },
};
// 이미 걸리는 것(면적·설비 불일치) → 현장 → 행정 → 수요 순으로 급한 것부터
const TOPIC_ORDER: Exclude<Topic, 'other'>[] = [
  'area',
  'facility',
  'access',
  'use',
  'regulation',
  'demand',
];

export function getKeyConclusionItems(checks: string[]) {
  const sentences = [
    ...new Set(
      checks
        .flatMap((text) => text.split(/(?<=[.!?])\s+/))
        .map((text) => text.trim())
        .filter(Boolean)
    ),
  ];

  const others = sentences.filter(
    (sentence) =>
      !TOPIC_ORDER.some((topic) => TOPICS[topic].test.test(sentence))
  );

  return [
    ...TOPIC_ORDER.map((topic) => ({
      key: topic,
      topic,
      ...TOPICS[topic],
      sources: sentences.filter((sentence) =>
        TOPICS[topic].test.test(sentence)
      ),
    })).filter((item) => item.sources.length > 0),
    ...(others.length
      ? [
          {
            key: 'other',
            topic: 'other' as const,
            title: '추가로 확인할 것',
            how: others.join(' '),
            sources: [] as string[],
          },
        ]
      : []),
  ];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const nums = (v: unknown) =>
  (String(v ?? '').match(/\d+(?:\.\d+)?/g) ?? []).map(Number);

const FIT_LABEL: Record<string, string> = {
  kitchen: '주방',
  ventilation: '환기',
  water_supply: '급배수',
};

const BADGE_TEXT: Record<
  string,
  { text: string; color: string; wash: string; onDark: string }
> = {
  추천: { text: '추천', color: P.brand, wash: P.blueWash, onDark: '#BFD2FF' },
  조건부: {
    text: '조건부 추천',
    color: P.amber,
    wash: P.amberWash,
    onDark: '#FFCF7A',
  },
  보류: {
    text: '판단 보류',
    color: P.amber,
    wash: P.amberWash,
    onDark: '#FFCF7A',
  },
  비추천: { text: '비추천', color: P.caution, wash: P.rose, onDark: '#FFB3C0' },
};

// 받침에 따라 을/를
function withObject(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return word + (code >= 0 && code % 28 !== 0 ? '을' : '를');
}

function Chip({
  children,
  tone,
}: {
  children: ReactNode;
  tone: 'warn' | 'muted' | 'ok';
}) {
  const style =
    tone === 'warn'
      ? { color: P.amber, backgroundColor: P.amberWash }
      : tone === 'ok'
        ? { color: P.brand, backgroundColor: P.blueWash }
        : { color: '#4B5866', backgroundColor: '#E3E9F0' };
  return (
    <span
      className="rounded-full px-2.5 py-1 text-13 font-semibold whitespace-nowrap"
      style={style}
    >
      {children}
    </span>
  );
}

export default function KeyConclusion({
  name,
  industryCode,
  badge,
  checks,
  facts,
}: {
  name: string | null | undefined;
  industryCode?: string;
  badge?: string;
  // 후보의 위험·확인 조건과 결과 전체의 확인 조건 문장
  checks: string[];
  facts: FactIndex;
}) {
  const allFacts: FactView[] = [...facts.values()];
  const findFact = (metric: string, code?: string) =>
    allFacts.find(
      (f) =>
        f.metric === metric &&
        (code === undefined ||
          f.industry_code === code ||
          (isObj(f.value) && f.value.industry_code === code))
    );

  // 문장을 쟁점별로 묶은 실제 표시 항목 수를 버튼 문구와 공유한다.
  const items = getKeyConclusionItems(checks);

  const spaceFit = industryCode
    ? findFact('space_fit', industryCode)?.value
    : undefined;
  const requirement = industryCode
    ? findFact('space_requirements', industryCode)?.value
    : undefined;
  const myArea = findFact('exclusive_area')?.value;

  function AreaEvidence() {
    const [mine] = nums(myArea);
    const [low, high] = isObj(requirement) ? nums(requirement.area_band) : [];
    if (!mine || !low || !high) return null;
    const max = Math.max(mine, high) * 1.15;
    const pct = (n: number) => `${(n / max) * 100}%`;
    const inside = mine >= low && mine <= high;
    return (
      <div className="flex w-full max-w-[420px] flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-13">
          <span className="text-[#66758A]">
            업종 권장 {low}~{high}㎡
          </span>
          <span
            className="font-bold"
            style={{ color: inside ? P.brand : P.amber }}
          >
            이 상가 {String(myArea)} · {inside ? '범위 안' : '범위 밖'}
          </span>
        </div>
        <div className="relative h-2.5 rounded-full bg-[#E3E9F0]">
          <span
            className="absolute top-0 bottom-0 rounded-full"
            style={{
              left: pct(low),
              width: pct(high - low),
              backgroundColor: inside ? '#9DB6F0' : '#F3C77E',
            }}
          />
          <span
            className="absolute -top-1.5 -bottom-1.5 w-0.5 -translate-x-1/2 rounded bg-[#10233A]"
            style={{ left: pct(mine) }}
          />
        </div>
      </div>
    );
  }

  function Evidence({ topic }: { topic: Topic }) {
    if (topic === 'area') return <AreaEvidence />;
    if (topic === 'facility' && isObj(spaceFit)) {
      const rows = Object.entries(FIT_LABEL).filter(
        ([key]) => spaceFit[key] && spaceFit[key] !== '해당 없음'
      );
      if (!rows.length) return null;
      return (
        <div className="flex flex-wrap gap-1.5 sm:justify-end">
          {rows.map(([key, label]) => {
            const state = String(spaceFit[key]);
            return (
              <Chip
                key={key}
                tone={
                  state === '일치'
                    ? 'ok'
                    : state === '불일치'
                      ? 'warn'
                      : 'muted'
                }
              >
                {label} {state === '일치' ? '갖춤' : state}
              </Chip>
            );
          })}
        </div>
      );
    }
    if (topic === 'use')
      return <Chip tone="muted">분석에서 확인하지 않음</Chip>;
    if (topic === 'demand')
      return <Chip tone="muted">수요 자료가 충분하지 않음</Chip>;
    return null;
  }

  const badgeText = badge ? BADGE_TEXT[badge] : undefined;

  return (
    <div className="key-conclusion flex w-full flex-col overflow-hidden border border-[#E3E9F0]">
      {/* ① 결론 패널 — 리포트에서 가장 먼저 읽혀야 하는 곳이라 유일하게 짙은 면으로 띄운다 */}
      <section className="key-conclusion-recommendation relative overflow-hidden bg-[#0C1936] px-6 py-8 text-white sm:px-10 sm:py-10">
        {/* 오로라 배경 — 모서리에만 빛이 은은하게 번진다 */}
        <span
          aria-hidden
          className="key-conclusion-glow pointer-events-none absolute inset-0"
          style={{
            background: [
              'radial-gradient(60% 90% at 90% 0%, rgba(46,82,190,0.42) 0%, rgba(46,82,190,0) 60%)',
              'radial-gradient(50% 80% at 5% 110%, rgba(33,64,160,0.38) 0%, rgba(33,64,160,0) 60%)',
              'linear-gradient(135deg, #0F1D45 0%, #0A1631 100%)',
            ].join(','),
          }}
        />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-14">
          <div className="key-conclusion-recommendation-primary flex flex-col gap-3">
            <p className="key-conclusion-recommendation-label flex items-center gap-2 text-sm font-bold text-[#9FB4D6]">
              <Building2 size={17} aria-hidden />
              가장 먼저 검토할 업종
            </p>
            <div className="key-conclusion-recommendation-title-row flex flex-wrap items-center gap-2">
              <h3 className="break-keep text-3xl leading-[1.2] font-extrabold tracking-[-0.03em] sm:text-32">
                {name ?? '추천 결과 없음'}
              </h3>
              {badgeText && (
                <span
                  className="key-conclusion-recommendation-badge mt-1 inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold"
                  style={{
                    color: '#10233A',
                    backgroundColor: badgeText.onDark,
                  }}
                >
                  <span className="key-conclusion-badge-desktop">
                    {badgeText.text}
                  </span>
                  <span className="key-conclusion-badge-mobile">
                    {badgeText.text === '추천' ? '상위 추천' : badgeText.text}
                  </span>
                </span>
              )}
            </div>
          </div>

          {name && (
            <div className="key-conclusion-direction flex flex-col gap-3">
              <p className="key-conclusion-direction-label text-sm font-bold text-[#9FB4D6]">
                검토 방향
              </p>
              <p className="key-conclusion-direction-copy break-keep text-xl leading-[1.6] font-bold tracking-[-0.02em] sm:text-22">
                <span className="key-conclusion-direction-desktop">
                  {withObject(name)} 먼저 검토하되,{' '}
                  <span className="text-[#FFCF7A]">
                    {items.length > 0
                      ? `아래 ${items.length}가지를 직접 확인한 뒤`
                      : '현장을 직접 확인한 뒤'}
                  </span>{' '}
                  결정하세요.
                </span>
                <span className="key-conclusion-direction-mobile">
                  먼저 살펴보되,{' '}
                  <span className="text-[#FFCF7A]">
                    {items.length > 0
                      ? `아래 ${items.length}가지를 확인한 뒤`
                      : '현장을 직접 확인한 뒤'}
                  </span>{' '}
                  결정하세요.
                </span>
              </p>
            </div>
          )}
        </div>
        {/* 검토 방향의 "N가지"에서 아래 확인 목록으로 이어지는 점선 */}
        {items.length > 0 && (
          <span
            aria-hidden
            className="key-conclusion-connector absolute bottom-0 left-[calc(1.5rem+11px)] h-8 border-l-2 border-dashed border-[#FFCF7A]/70 sm:left-[calc(2.5rem+11px)]"
          />
        )}
      </section>

      {/* ② 입점 전 확인할 N가지 — 이 장의 중심 */}
      <section
        id="key-checks"
        className="key-conclusion-checks flex scroll-mt-28 flex-col gap-5 bg-white px-6 pb-8 sm:px-10 sm:pb-10"
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            {items.length > 0 ? (
              <span
                aria-hidden
                className="ml-[11px] h-6 border-l-2 border-dashed border-[#E2B45C]/70"
              />
            ) : (
              <span aria-hidden className="h-8" />
            )}
            <h3 className="flex items-center gap-2 text-xl font-extrabold tracking-[-0.02em] text-[#10233A] sm:text-2xl">
              <TriangleAlert
                className="key-conclusion-warning-desktop"
                size={22}
                color={P.amber}
                aria-hidden
              />
              <span
                className="key-conclusion-warning-mobile"
                aria-hidden="true"
              >
                !
              </span>
              {items.length > 0
                ? `입점 전 확인할 ${items.length}가지`
                : '입점 전 직접 확인하세요'}
            </h3>
            <p className="key-conclusion-checks-intro text-15 text-[#5B6470]">
              분석 자료로는 알 수 없어 현장에서 봐야 하는 것들이에요.
            </p>
            <p className="key-conclusion-checks-intro-mobile text-15 text-[#5B6470]">
              분석 자료로 알 수 없는 조건은 현장에서 확인하세요.
            </p>
          </div>
        </div>

        {items.length === 0 ? (
          <p className="text-15 py-4 text-[#4B5866]">
            분석 결과에 별도 조건이 기재되지 않았어요. 현장에서 입점 조건을
            확인하세요.
          </p>
        ) : (
          <ol className="-my-2 flex flex-col">
            {items.map((item, i) => {
              return (
                <li
                  key={item.key}
                  className="key-conclusion-check-item grid grid-cols-[40px_1fr] gap-x-4 gap-y-3 py-6 sm:grid-cols-[44px_1fr_minmax(0,400px)] sm:gap-x-6"
                >
                  <span className="key-conclusion-check-number text-2xl leading-none font-extrabold tabular-nums text-[#2453D6] sm:pt-0.5">
                    {String(i + 1).padStart(2, '0')}
                  </span>

                  <div className="key-conclusion-check-copy flex min-w-0 flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-lg font-extrabold tracking-[-0.01em] text-[#10233A]">
                        {item.title}
                      </p>
                      {i === 0 && (
                        <span className="text-13 rounded-full bg-[#10233A] px-2.5 py-0.5 font-bold text-white">
                          가장 먼저
                        </span>
                      )}
                    </div>
                    <p className="text-base break-keep leading-[1.7] text-[#3D4A5C]">
                      {item.how}
                    </p>
                  </div>

                  <div className="key-conclusion-evidence col-start-2 flex items-start sm:col-start-3 sm:justify-end sm:pt-1.5">
                    <Evidence topic={item.topic} />
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}
