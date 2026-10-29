'use client';

import { useState, type ReactNode } from 'react';
import {
  ArrowRight,
  Building2,
  Check,
  ChevronRight,
  ClipboardCheck,
  DoorOpen,
  Fan,
  FileSearch,
  Ruler,
  ShieldAlert,
  TriangleAlert,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { reportPalette as P } from '@/styles/reportPalette';
import type { FactIndex } from '@/lib/api/segments';
import type { FactView } from '@/lib/api/types';

/**
 * 02 핵심 결론.
 *
 * - 1행: 가장 먼저 검토할 업종 | 검토 방향 (카드·구분선 없이 같은 행)
 * - 추천 근거 한 줄
 * - 입점 전 직접 확인하세요: 이 장의 중심. 후보의 위험·확인 조건 문장을 쟁점별로
 *   묶고, fact로 읽히는 근거를 붙이고, 임대인이 체크하며 내려갈 수 있게 한다.
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
  { title: string; Icon: LucideIcon; test: RegExp; how: string }
> = {
  area: {
    title: '실제로 쓸 수 있는 면적',
    Icon: Ruler,
    test: /면적|구획|실측/,
    how: '도면과 현장 실측으로 기둥·복도를 뺀 사용 면적을 재고, 업종에 맞게 나눠 쓸 수 있는지 확인하세요.',
  },
  facility: {
    title: '주방·환기·급배수 설비',
    Icon: Fan,
    test: /환기|배기|급수|급배수|주방|설비|전력/,
    how: '이 업종에 필요한 설비를 지금 쓸 수 있는지, 없다면 설치 위치와 비용을 설비 업체에 확인하세요.',
  },
  access: {
    title: '드나들기 쉬운지와 간판 노출',
    Icon: DoorOpen,
    test: /엘리베이터|동선|간판|노출|접근/,
    how: '손님이 입구와 엘리베이터를 쉽게 찾을 수 있는지, 간판을 어디에 달 수 있는지 현장에서 확인하세요.',
  },
  use: {
    title: '건축물 용도와 인허가',
    Icon: FileSearch,
    test: /용도|인허가|허가/,
    how: '건축물대장에서 용도를 확인하고, 이 업종으로 영업 신고·인허가가 되는지 관할 구청에 문의하세요.',
  },
  regulation: {
    title: '입점 규제',
    Icon: ShieldAlert,
    test: /보호구역|규제|제한/,
    how: '학교 주변 보호구역 등으로 이 업종의 영업이 제한되지 않는지 관할 구청이나 교육지원청에 확인하세요.',
  },
  demand: {
    title: '이 업종을 찾을 손님',
    Icon: Users,
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

const BADGE_TEXT: Record<string, { text: string; color: string }> = {
  추천: { text: '추천', color: P.brand },
  조건부: { text: '조건부 추천', color: P.amber },
  보류: { text: '판단 보류', color: P.amber },
  비추천: { text: '비추천', color: P.caution },
};

// 받침에 따라 을/를
function withObject(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return word + (code >= 0 && code % 28 !== 0 ? '을' : '를');
}

// 근거 보기 링크가 가리킬 분석 장
function reasonTarget(reason: string) {
  if (/폐업|개업|증가|감소|추이/.test(reason)) return '#lifecycle';
  if (/인구|연령|통행/.test(reason)) return '#customers';
  return '#competition';
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
  nextNames,
  reason,
  checks,
  facts,
}: {
  name: string | null | undefined;
  industryCode?: string;
  badge?: string;
  nextNames: string[];
  reason: string;
  // 후보의 위험·확인 조건과 결과 전체의 확인 조건 문장
  checks: string[];
  facts: FactIndex;
}) {
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const allFacts: FactView[] = [...facts.values()];
  const findFact = (metric: string, code?: string) =>
    allFacts.find(
      (f) =>
        f.metric === metric &&
        (code === undefined ||
          f.industry_code === code ||
          (isObj(f.value) && f.value.industry_code === code))
    );

  // 문장을 쪼개 쟁점별로 나눈다. 한 문장이 여러 쟁점에 걸칠 수 있다.
  const sentences = [
    ...new Set(
      checks
        .flatMap((text) => text.split(/(?<=[.다요])\s*(?=[가-힣A-Z])/))
        .map((text) => text.trim())
        .filter(Boolean)
    ),
  ];
  const items: {
    key: string;
    topic: Topic;
    title: string;
    how: string;
    Icon: LucideIcon;
    sources: string[];
  }[] = [
    ...TOPIC_ORDER.map((topic) => ({
      key: topic,
      topic,
      ...TOPICS[topic],
      sources: sentences.filter((s) => TOPICS[topic].test.test(s)),
    })).filter((item) => item.sources.length > 0),
    // 어느 쟁점에도 안 걸린 문장은 그대로 한 항목씩 보여 준다
    ...sentences
      .filter((s) => !TOPIC_ORDER.some((t) => TOPICS[t].test.test(s)))
      .map((s, i) => ({
        key: `other-${i}`,
        topic: 'other' as const,
        title: '추가로 확인할 것',
        how: s,
        Icon: ClipboardCheck,
        sources: [],
      })),
  ];

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

  const toggle = (key: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const done = items.filter((item) => checked.has(item.key)).length;
  const allDone = items.length > 0 && done === items.length;
  const [reasonLead] = reason.split(/(?<=\.)\s+/);
  const badgeText = badge ? BADGE_TEXT[badge] : undefined;
  const mark =
    'linear-gradient(transparent 58%, #FFE1A6 58%, #FFE1A6 92%, transparent 92%)';

  return (
    <div className="flex w-full flex-col">
      {/* ① 같은 행: 가장 먼저 검토할 업종 | 검토 방향 */}
      <section className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <div className="flex flex-col gap-3">
          <p className="flex items-center gap-2 text-sm font-bold text-[#66758A]">
            <Building2 size={18} aria-hidden />
            가장 먼저 검토할 업종
          </p>
          <h3 className="text-34 sm:text-44 break-keep leading-[1.2] font-extrabold tracking-[-0.03em] text-[#10233A]">
            {name ?? '추천 결과 없음'}
          </h3>
          {badgeText && (
            <p className="text-15 font-bold" style={{ color: badgeText.color }}>
              {badgeText.text}
            </p>
          )}
          {nextNames.length > 0 && (
            <p className="mt-2 text-sm text-[#8A97A5]">
              다음 후보 · {nextNames.join(' · ')}
            </p>
          )}
        </div>

        {name && (
          <div className="flex flex-col gap-3">
            <p className="text-sm font-bold text-[#66758A]">검토 방향</p>
            <p className="sm:text-27 text-2xl break-keep leading-[1.5] font-bold tracking-[-0.02em] text-[#10233A]">
              {withObject(name)} 먼저 검토하되,{' '}
              {items.length > 0 ? (
                <>
                  <span
                    style={{
                      backgroundImage: mark,
                      boxDecorationBreak: 'clone',
                      WebkitBoxDecorationBreak: 'clone',
                    }}
                  >
                    아래 {items.length}가지를 직접 확인한 뒤
                  </span>{' '}
                  결정하세요.
                </>
              ) : (
                <span
                  style={{
                    backgroundImage: mark,
                    boxDecorationBreak: 'clone',
                    WebkitBoxDecorationBreak: 'clone',
                  }}
                >
                  현장을 직접 확인한 뒤 결정하세요.
                </span>
              )}
            </p>
          </div>
        )}
      </section>

      {/* ② 추천 근거 — 한 줄 */}
      {reason && (
        <section className="mt-12 grid gap-3 sm:grid-cols-[160px_1fr_auto] sm:items-baseline sm:gap-8">
          <p className="text-sm font-bold text-[#66758A]">추천 근거</p>
          <p className="text-17 break-keep leading-[1.7] text-[#1F2D3D]">
            {reasonLead}
          </p>
          <a
            href={reasonTarget(reason)}
            className="text-15 inline-flex items-center gap-1 font-semibold whitespace-nowrap text-[#2453D6]"
          >
            근거 보기 <ChevronRight size={16} aria-hidden />
          </a>
        </section>
      )}

      {/* ③ 입점 전 직접 확인하세요 — 이 장의 중심 */}
      <section className="mt-20 flex flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <h3 className="sm:text-27 flex items-center gap-2.5 text-2xl font-extrabold tracking-[-0.02em] text-[#10233A]">
              <TriangleAlert size={26} color={P.amber} aria-hidden />
              입점 전 직접 확인하세요.
            </h3>
            <p className="text-base text-[#5B6470]">
              현장에서 확인한 항목은 체크해 두세요.
            </p>
          </div>
          {items.length > 0 && (
            <div
              className="report-screen-only flex min-w-[180px] flex-col gap-2"
              aria-live="polite"
            >
              <p className="text-sm font-semibold text-[#4B5866]">
                <span className="text-lg font-extrabold text-[#10233A]">
                  {done}
                </span>{' '}
                / {items.length} 확인
              </p>
              <div className="h-1.5 overflow-hidden rounded-full bg-[#E3E9F0]">
                <span
                  className="block h-full rounded-full bg-[#2453D6] transition-[width] duration-300"
                  style={{ width: `${(done / items.length) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {items.length === 0 ? (
          <p className="text-15 rounded-[24px] bg-[#EAF0F6] px-6 py-8 text-[#4B5866]">
            분석 결과에 별도 조건이 기재되지 않았어요. 현장에서 입점 조건을
            확인하세요.
          </p>
        ) : (
          <ol className="flex flex-col gap-1 rounded-[24px] bg-[#EAF0F6] px-4 py-3 sm:px-8 sm:py-4">
            {items.map((item, i) => {
              const isDone = checked.has(item.key);
              return (
                <li
                  key={item.key}
                  className="grid grid-cols-[44px_1fr] gap-x-4 gap-y-3 py-7 sm:grid-cols-[52px_1fr_minmax(0,420px)] sm:gap-x-6"
                >
                  <button
                    type="button"
                    onClick={() => toggle(item.key)}
                    aria-pressed={isDone}
                    aria-label={`${item.title} 확인 ${isDone ? '취소' : '완료'}`}
                    className="flex size-11 items-center justify-center rounded-full border-2 transition-colors sm:size-12"
                    style={
                      isDone
                        ? {
                            backgroundColor: P.brand,
                            borderColor: P.brand,
                            color: '#fff',
                          }
                        : {
                            backgroundColor: '#fff',
                            borderColor: '#C9D2DC',
                            color: '#8A97A5',
                          }
                    }
                  >
                    {isDone ? (
                      <Check size={22} strokeWidth={3} aria-hidden />
                    ) : (
                      <item.Icon size={20} aria-hidden />
                    )}
                  </button>

                  <div className="flex min-w-0 flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-[#8A97A5] tabular-nums">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <p
                        className={`text-xl font-extrabold tracking-[-0.01em] ${
                          isDone
                            ? 'text-[#8A97A5] line-through decoration-2'
                            : 'text-[#10233A]'
                        }`}
                      >
                        {item.title}
                      </p>
                      {i === 0 && !isDone && (
                        <span className="text-13 rounded-full bg-[#10233A] px-2.5 py-0.5 font-bold text-white">
                          가장 먼저
                        </span>
                      )}
                    </div>
                    <p className="text-17 break-keep leading-[1.7] text-[#3D4A5C]">
                      {item.how}
                    </p>
                  </div>

                  <div className="col-start-2 flex items-start sm:col-start-3 sm:justify-end sm:pt-1.5">
                    <Evidence topic={item.topic} />
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        <div className="report-screen-only flex justify-end px-2">
          <a
            href="#listing"
            className="text-15 inline-flex items-center gap-2 rounded-full px-5 py-2.5 font-bold transition-colors"
            style={
              allDone
                ? { backgroundColor: P.brand, color: '#fff' }
                : {
                    backgroundColor: '#fff',
                    color: '#10233A',
                    border: `1px solid ${P.line}`,
                  }
            }
          >
            임차인 찾기
            <ArrowRight size={18} aria-hidden />
          </a>
        </div>
      </section>
    </div>
  );
}
