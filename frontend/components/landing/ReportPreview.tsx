'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ArrowRight, Building2, FileText, TriangleAlert } from 'lucide-react';
import { mockReportData } from '@/lib/mockData/report';
import {
  mockCompetitionFacts,
  mockFloatingPopulationFacts,
  mockLifecycleFacts,
  mockRecommendedIndustryCodes,
} from '@/lib/mockData/reportPresentation';

/**
 * 랜딩 "분석 리포트 미리보기" 섹션 (#report-preview).
 *
 * 히어로의 "리포트 예시 보기"가 이 섹션으로 내려온다. 한 화면에 고정된 무대에서
 * 5초마다 다음 단계(답 → 상권 → 검증)가 아래에서 위로 올라오고, 각 단계에는 리포트
 * 화면 축소판(채움 분석 리포트 · 예시)이 함께 보인다. 섹션이 화면에 보일 때만
 * 넘어가고, 마우스를 올리면 멈춘다. 마지막에 "내 상가로 분석해 보기"로 이어진다.
 *
 * 수치는 리포트 목업과 같은 값을 쓴다. 주소는 넣지 않는다. 면적·평가자 판정 등
 * 일부 문구는 화면 구성을 보여주는 예시다.
 */

const top3 = mockReportData.recommended.slice(0, 3);

const STEPS = [
  {
    key: 'answer',
    label: '답',
    title: '무엇을 들이면 좋을지\n먼저 알려드려요',
    desc: '가장 먼저 검토할 업종과, 계약 전에 꼭 확인할 것을 한 화면에 정리해요.',
  },
  {
    key: 'why',
    label: '상권',
    title: '내 상가 주변을\n데이터로 읽어드려요',
    desc: '내 상가 반경 안의 유동인구, 같은 업종 경쟁, 개폐업 흐름을 리포트 한 장씩으로 정리해요.',
  },
  {
    key: 'check',
    label: '검증',
    title: '네 사람의 눈으로\n한 번 더 따져봐요',
    desc: '심사위원·창업자·고객·임대인 대변인이 각자 입장에서 추천을 다시 검토해요.',
  },
] as const;

// ── 축소판 화면 3개 ────────────────────────────────────────────
function Frame({
  children,
  caption,
}: {
  children: ReactNode;
  caption: string;
}) {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-[0_18px_38px_rgba(0,0,0,0.24)] sm:rounded-[20px] sm:shadow-[0_30px_60px_rgba(0,0,0,0.28)]">
      <div className="flex items-center justify-between gap-2 border-b border-[#EEF1F5] bg-[#F3F6FA] px-3 py-2.5 sm:gap-3 sm:px-5 sm:py-3">
        <span className="flex items-center gap-1.5 sm:gap-2">
          <FileText
            size={14}
            className="text-[#2453D6] sm:size-4"
            aria-hidden
          />
          <span className="text-xs font-extrabold text-[#10233A] sm:text-13">
            채움 분석 리포트
          </span>
          <span className="rounded bg-[#10233A] px-1.5 py-0.5 text-[10px] font-bold text-white sm:text-[11px]">
            예시
          </span>
        </span>
        <span className="text-[10px] font-bold text-[#2453D6] sm:text-xs">
          {caption}
        </span>
      </div>
      {children}
    </div>
  );
}

function AnswerScreen() {
  return (
    <Frame caption="02 핵심 결론">
      <div
        className="relative px-4 py-4 text-white sm:px-6 sm:py-6"
        style={{
          background: [
            'radial-gradient(60% 90% at 90% 0%, rgba(46,82,190,0.42) 0%, rgba(46,82,190,0) 60%)',
            'linear-gradient(135deg, #0F1D45 0%, #0A1631 100%)',
          ].join(','),
        }}
      >
        <p className="flex items-center gap-1.5 text-xs font-bold text-[#9FB4D6] sm:text-13">
          <Building2 size={14} className="sm:size-[15px]" aria-hidden /> 가장
          먼저 검토할 업종
        </p>
        <p className="mt-1.5 text-xl font-extrabold tracking-[-0.03em] sm:mt-2 sm:text-2xl">
          {top3[0].name}
        </p>
        <span className="mt-1.5 inline-flex rounded-full bg-[#FFCF7A] px-2.5 py-0.5 text-xs font-bold text-[#10233A] sm:mt-2 sm:text-13">
          조건부 추천
        </span>
        <p className="mt-3 text-sm leading-[1.55] font-bold sm:mt-4 sm:text-base sm:leading-[1.6]">
          {top3[0].name}를 먼저 검토하되,{' '}
          <span className="text-[#FFCF7A]">아래 2가지를 직접 확인한 뒤</span>{' '}
          결정하세요.
        </p>
        <span
          aria-hidden
          className="absolute bottom-0 left-[calc(1.5rem+9px)] h-6 border-l-2 border-dashed border-[#FFCF7A]/70"
        />
      </div>
      <div className="px-4 pb-4 sm:px-6 sm:pb-6">
        <span
          aria-hidden
          className="ml-[9px] block h-4 border-l-2 border-dashed border-[#E2B45C]/70"
        />
        <p className="flex items-center gap-1.5 text-sm font-extrabold text-[#10233A] sm:text-base">
          <TriangleAlert
            size={16}
            className="sm:size-[18px]"
            color="#A65B00"
            aria-hidden
          />
          입점 전 확인할 2가지
        </p>
        <ol className="mt-2.5 flex flex-col gap-2 sm:mt-3 sm:gap-3">
          {[
            [
              '출입구와 간판 노출',
              '1층 출입구에서 매장이 잘 보이고 찾아오기 쉬운지 확인하세요.',
            ],
            [
              '실제로 쓸 수 있는 면적',
              '넓은 공간을 나눠 쓸 수 있는지 도면으로 확인하세요.',
            ],
          ].map(([t, d], i) => (
            <li key={t} className="grid grid-cols-[32px_1fr] gap-x-2">
              <span className="text-base leading-none font-extrabold text-[#2453D6] sm:text-lg">
                0{i + 1}
              </span>
              <div>
                <p className="text-sm font-bold text-[#10233A] sm:text-15">
                  {t}
                </p>
                <p className="text-xs leading-4 text-[#4B5866] sm:text-13 sm:leading-5">
                  {d}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Frame>
  );
}

// 상권 탭 — 리포트 05·06·07장의 첫 화면(한 줄 결론 + 핵심 지표)을 그대로 줄인 것.
// 값은 리포트 목업 화면과 같다.
const TABS = ['유동인구', '경쟁 업체', '개폐업'] as const;

const AGES = mockFloatingPopulationFacts.ageShares;
const TOP_AGE = AGES.reduce((best, age) =>
  age.share > best.share ? age : best
);

const COMPETITION = [
  ...mockCompetitionFacts.selected
    .filter((row) => mockRecommendedIndustryCodes.has(row.code))
    .slice(0, 2),
  ...mockCompetitionFacts.selected
    .filter((row) => !mockRecommendedIndustryCodes.has(row.code))
    .slice(0, 2),
];
const LIFECYCLE_EXAMPLE = mockLifecycleFacts.rows[0];
const LIFECYCLE_METRICS = [
  {
    label: '평균 점포 수',
    value: LIFECYCLE_EXAMPLE.avgStoreCount?.toFixed(1),
  },
  {
    label: '회전율',
    value:
      LIFECYCLE_EXAMPLE.turnoverRate === null
        ? undefined
        : `${LIFECYCLE_EXAMPLE.turnoverRate.toFixed(1)}%`,
  },
  {
    label: '서울 대비 폐업률',
    value:
      LIFECYCLE_EXAMPLE.closeRateRatio === null
        ? undefined
        : `${LIFECYCLE_EXAMPLE.closeRateRatio.toFixed(2)}배`,
  },
  {
    label: '순증감률',
    value:
      LIFECYCLE_EXAMPLE.netChangeRate === null
        ? undefined
        : `${LIFECYCLE_EXAMPLE.netChangeRate > 0 ? '+' : ''}${LIFECYCLE_EXAMPLE.netChangeRate.toFixed(1)}%`,
  },
];

function Ratio({ value }: { value: number }) {
  const up = value > 1;
  return (
    <span
      className="rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums sm:px-2 sm:text-xs"
      style={
        up
          ? { color: '#C2410C', background: '#FFEDD5' }
          : { color: '#2453D6', background: '#EAF0FC' }
      }
    >
      {up ? '▲' : '▼'} {value.toFixed(2)}배
    </span>
  );
}

function WhyScreen() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('유동인구');
  return (
    <Frame caption="05 · 06 · 07 상권 분석">
      <div className="flex flex-col gap-3 px-4 py-4 sm:gap-5 sm:px-6 sm:py-6">
        <div
          role="tablist"
          className="flex gap-1 rounded-full bg-[#F1F4F8] p-1"
        >
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className="flex-1 rounded-full py-1.5 text-xs font-bold transition-colors sm:py-2 sm:text-13"
              style={
                tab === t
                  ? {
                      background: '#fff',
                      color: '#10233A',
                      boxShadow: '0 2px 6px rgba(16,35,58,0.1)',
                    }
                  : { color: '#66758A' }
              }
            >
              {t}
            </button>
          ))}
        </div>

        {tab === '유동인구' && (
          <div className="flex flex-col gap-3 sm:gap-5">
            {/* 리포트 05장과 같은 상권 유형 일러스트(주거생활형) */}
            <div className="flex items-center justify-between gap-4">
              <p className="text-base leading-snug font-extrabold text-[#10233A] sm:text-lg">
                이 주변은
                <br />
                <span className="text-[#2453D6]">주거생활형</span> 상권이에요
              </p>
              <Image
                src="/images/area-types/residential.webp"
                alt="주거생활형 상권 일러스트"
                width={720}
                height={427}
                className="h-auto w-[120px] shrink-0 sm:w-[170px]"
              />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div className="rounded-xl bg-[#10233A] px-3 py-2.5 text-white sm:px-4 sm:py-3">
                <p className="text-xs font-semibold text-[#9FB4D6]">
                  하루 평균 유동인구
                </p>
                <p className="mt-1 text-xl font-extrabold sm:text-2xl">
                  {mockFloatingPopulationFacts.dailyPerTradeArea === null
                    ? '—'
                    : Math.round(
                        mockFloatingPopulationFacts.dailyPerTradeArea
                      ).toLocaleString('ko-KR')}
                  <span className="ml-0.5 text-sm font-bold">명/일</span>
                </p>
              </div>
              <div className="rounded-xl border border-[#E3E9F0] px-3 py-2.5 sm:px-4 sm:py-3">
                <p className="text-xs font-semibold text-[#66758A]">
                  가장 많은 연령대
                </p>
                <p className="mt-1 text-xl font-extrabold text-[#10233A] sm:text-2xl">
                  {TOP_AGE.label}
                  <span className="ml-1 text-sm font-bold">
                    {(TOP_AGE.share * 100).toFixed(1)}%
                  </span>
                </p>
              </div>
            </div>
            <ul className="flex flex-col gap-1.5">
              {AGES.map((age) => (
                <li
                  key={age.label}
                  className="grid grid-cols-[44px_minmax(0,1fr)_42px] items-center gap-1 text-[11px] sm:grid-cols-[56px_1fr_52px] sm:gap-2 sm:text-xs"
                >
                  <span className="font-bold text-[#10233A]">{age.label}</span>
                  <span className="h-1.5 rounded-full bg-[#EEF2F6]">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${(age.share / TOP_AGE.share) * 100}%`,
                        background:
                          age.label === TOP_AGE.label ? '#2453D6' : '#8DA2C4',
                      }}
                    />
                  </span>
                  <span className="text-right font-semibold tabular-nums text-[#4B5866]">
                    {(age.share * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
            <p className="-mt-1 text-[10px] text-[#8A97A5] sm:text-[11px]">
              구성비 · 주변 상권 유동인구
            </p>
          </div>
        )}

        {tab === '경쟁 업체' && (
          <div className="flex flex-col gap-3 sm:gap-5">
            <p className="text-base leading-snug font-extrabold text-[#10233A] sm:text-lg">
              주변에는{' '}
              <span
                className={
                  mockRecommendedIndustryCodes.has(COMPETITION[0]?.code ?? '')
                    ? 'text-[#2453D6]'
                    : 'text-[#66758A]'
                }
              >
                {COMPETITION[0]?.name}
              </span>{' '}
              {COMPETITION[0]?.storeCount == null
                ? '자료 없음'
                : `${COMPETITION[0]?.storeCount}곳`}
              ,{' '}
              <span
                className={
                  mockRecommendedIndustryCodes.has(COMPETITION[1]?.code ?? '')
                    ? 'text-[#2453D6]'
                    : 'text-[#66758A]'
                }
              >
                {COMPETITION[1]?.name}
              </span>{' '}
              {COMPETITION[1]?.storeCount == null
                ? '자료 없음'
                : `${COMPETITION[1]?.storeCount}곳`}
              이 있어요.
            </p>
            <table className="w-full text-[11px] sm:text-13">
              <thead>
                <tr className="text-xs text-[#8A97A5]">
                  <th className="pb-2 text-left font-semibold sm:pb-3">업종</th>
                  <th className="pb-2 text-right font-semibold sm:pb-3">
                    동종 점포
                  </th>
                  <th className="pb-2 text-right font-semibold sm:pb-3">
                    반경 2km 대비
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPETITION.map((row) => (
                  <tr key={row.code} className="border-t border-[#EEF1F5]">
                    <td
                      className={`py-3 sm:py-[18px] ${mockRecommendedIndustryCodes.has(row.code) ? 'font-bold text-[#10233A]' : 'text-[#66758A]'}`}
                    >
                      {row.name}
                      {!mockRecommendedIndustryCodes.has(row.code) && (
                        <span className="ml-1 text-[9px] text-[#8A97A5] sm:ml-1.5 sm:text-[11px]">
                          제외 후보
                        </span>
                      )}
                    </td>
                    <td className="py-3 text-right tabular-nums text-[#4B5866] sm:py-[18px]">
                      {row.storeCount === null
                        ? '자료 없음'
                        : `${row.storeCount}개`}
                    </td>
                    <td className="py-3 text-right sm:py-[18px]">
                      {row.lq !== null && <Ratio value={row.lq} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === '개폐업' && (
          <div className="flex flex-col gap-3 sm:gap-5">
            <p className="text-base leading-snug font-extrabold text-[#10233A] sm:text-lg">
              {LIFECYCLE_EXAMPLE.name} 최근 1년 폐업률은{' '}
              <span className="text-[#2453D6]">
                {LIFECYCLE_EXAMPLE.recentCloseRate === null
                  ? '자료 없음'
                  : `${LIFECYCLE_EXAMPLE.recentCloseRate.toFixed(1)}%`}
              </span>
              이에요.
            </p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              {LIFECYCLE_METRICS.map(({ label, value }) => (
                <div key={label} className="border-t border-[#EEF1F5] pt-2">
                  <dt className="text-xs text-[#66758A]">{label}</dt>
                  <dd className="mt-1 text-base font-extrabold tabular-nums text-[#10233A]">
                    {value ?? '자료 없음'}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </Frame>
  );
}

const REVIEWERS = [
  {
    name: '심사위원',
    avatar: 'examiner',
    v: '조건부 동의',
    c: '#F0A43A',
    t: '#A65B00',
  },
  {
    name: '창업자',
    avatar: 'founder',
    v: '조건부 동의',
    c: '#F0A43A',
    t: '#A65B00',
  },
  { name: '고객', avatar: 'customer', v: '동의', c: '#2453D6', t: '#2453D6' },
  {
    name: '임대인 대변인',
    avatar: 'landlord-advocate',
    v: '반대',
    c: '#D9586C',
    t: '#9B3545',
  },
];

function CheckScreen() {
  return (
    <Frame caption="04 교차 검토">
      <div className="flex flex-col gap-3 px-4 py-4 sm:gap-5 sm:px-6 sm:py-6">
        <div>
          <span className="block h-6 font-serif text-[42px] leading-none font-black text-[#F0A43A] sm:h-8 sm:text-[56px]">
            &ldquo;
          </span>
          <p className="text-base leading-[1.45] font-extrabold tracking-[-0.02em] text-[#10233A] sm:text-lg">
            추천 업종은 바로 정하기보다,{' '}
            <span
              style={{
                backgroundImage:
                  'linear-gradient(transparent 58%, #FFE1A6 58%, #FFE1A6 92%, transparent 92%)',
              }}
            >
              조건을 확인한 뒤 결정하라
            </span>
            는 의견이 많아요
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex h-2 gap-1">
            {REVIEWERS.map((r) => (
              <span
                key={r.name}
                className="flex-1 first:rounded-l-full last:rounded-r-full"
                style={{ background: r.c }}
              />
            ))}
          </div>
          <ul className="grid grid-cols-4 gap-1">
            {REVIEWERS.map((r) => (
              <li
                key={r.name}
                className="flex flex-col items-center gap-1 text-center"
              >
                <span
                  className="inline-flex size-9 overflow-hidden rounded-full bg-white sm:size-11"
                  style={{ boxShadow: `0 0 0 2.5px ${r.c}` }}
                >
                  <Image
                    src={`/images/review-avatars/${r.avatar}.svg`}
                    alt=""
                    width={44}
                    height={44}
                    unoptimized
                  />
                </span>
                <span className="mt-1 text-[10px] font-bold whitespace-nowrap text-[#10233A] sm:text-xs">
                  {r.name}
                </span>
                <span
                  className="text-[9px] font-semibold whitespace-nowrap sm:text-[11px]"
                  style={{ color: r.t }}
                >
                  {r.v}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="rounded-xl bg-[#EAF0F6] px-3 py-2.5 text-xs leading-4 text-[#3D4A5C] sm:px-4 sm:py-3 sm:text-13 sm:leading-5">
          <b className="text-[#10233A]">임대인 대변인</b> · 월세·보증금은
          분석하지 않으므로 매물 수익성은 따로 확인해야 한다고 봤어요.
        </p>
      </div>
    </Frame>
  );
}

const SCREENS = [AnswerScreen, WhyScreen, CheckScreen];

// 한 단계를 보여주는 시간. 글과 화면을 함께 읽을 수 있게 5초로 둔다.
const INTERVAL_MS = 5000;

export default function ReportPreview() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [inView, setInView] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  // 화면에 보일 때만 돌린다 — 안 보는 동안 넘어가 있으면 처음부터 못 본다
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { threshold: 0.5 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!inView || paused) return;
    const timer = window.setTimeout(
      () => setActive((i) => (i + 1) % STEPS.length),
      INTERVAL_MS
    );
    return () => window.clearTimeout(timer);
  }, [active, inView, paused]);

  return (
    <section
      id="report-preview"
      className="relative w-full scroll-mt-16 px-4 pt-16 pb-12 sm:px-8 sm:py-24"
      style={{ backgroundColor: '#10233A' }}
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="flex flex-col items-start">
          <p className="text-sm font-bold tracking-[0.08em] text-[#9DB5F2]">
            REPORT PREVIEW
          </p>
          <h2 className="mt-2.5 flex flex-wrap items-center gap-2 text-2xl leading-[1.25] font-extrabold tracking-[-0.02em] text-white sm:mt-3.5 sm:gap-3 sm:text-4xl sm:leading-[1.3]">
            분석 리포트 미리보기
            <span className="rounded-md bg-[#FFCF7A] px-2 py-0.5 text-xs font-extrabold tracking-normal text-[#10233A] sm:px-2.5 sm:py-1 sm:text-base">
              예시 리포트
            </span>
          </h2>
        </div>

        {/* 한 화면에 고정된 무대 — 3초마다 다음 단계가 아래에서 위로 올라온다 */}
        <div
          ref={stageRef}
          className="mt-8 grid gap-6 sm:mt-14 sm:gap-10 lg:grid-cols-[56px_minmax(0,1fr)] lg:gap-8"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
        >
          {/* 단계 표시 — 진행 막대가 차오르고, 눌러서 바로 이동할 수도 있다. 큰 화면에서는 무대 높이의 가운데에 둔다 */}
          <ol className="flex gap-2 sm:gap-3 lg:flex-col lg:gap-5 lg:self-center">
            {STEPS.map((s, i) => {
              const on = i === active;
              return (
                <li key={s.key} className="flex-1 lg:flex-none">
                  <button
                    type="button"
                    onClick={() => setActive(i)}
                    aria-current={on ? 'step' : undefined}
                    className="flex w-full flex-col items-start gap-2 text-left lg:items-center"
                  >
                    <span
                      className="text-sm font-bold transition-colors"
                      style={{ color: on ? '#FFCF7A' : '#5D6F8A' }}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="relative h-1 w-full overflow-hidden rounded-full bg-white/10 lg:h-28 lg:w-1">
                      {on && (
                        <span
                          key={`${active}-${paused}`}
                          className="rp-fill absolute inset-0 rounded-full bg-[#FFCF7A]"
                          style={{
                            animationDuration: `${INTERVAL_MS}ms`,
                            animationPlayState:
                              paused || !inView ? 'paused' : 'running',
                          }}
                        />
                      )}
                      {i < active && (
                        <span className="absolute inset-0 rounded-full bg-[#FFCF7A]/40" />
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          {/* 슬라이드 — 모두 같은 칸에 겹쳐 두고, 가장 큰 화면 높이로 무대를 고정한다 */}
          <div className="grid" aria-live="polite">
            {SCREENS.map((Screen, i) => {
              const state = i === active ? 'now' : i < active ? 'past' : 'next';
              return (
                <div
                  key={STEPS[i].key}
                  aria-hidden={state !== 'now'}
                  className="col-start-1 row-start-1 grid items-center gap-5 transition-[opacity,transform] duration-700 ease-[cubic-bezier(0.2,0.7,0.2,1)] motion-reduce:transition-none sm:gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16"
                  style={{
                    opacity: state === 'now' ? 1 : 0,
                    transform:
                      state === 'now'
                        ? 'translateY(0)'
                        : state === 'past'
                          ? 'translateY(-48px)'
                          : 'translateY(64px)',
                    pointerEvents: state === 'now' ? 'auto' : 'none',
                  }}
                >
                  <div>
                    <span className="rounded-full bg-[#FFCF7A] px-2.5 py-0.5 text-xs font-bold text-[#10233A] sm:px-3 sm:py-1 sm:text-sm">
                      {i + 1} · {STEPS[i].label}
                    </span>
                    <p className="mt-3 text-xl leading-[1.35] font-extrabold whitespace-pre-line text-white sm:mt-5 sm:text-3xl sm:leading-[1.4]">
                      {STEPS[i].title}
                    </p>
                    <p className="mt-2 max-w-[420px] text-sm leading-6 text-[#C3CCD8] sm:mt-3 sm:text-base sm:leading-7">
                      {STEPS[i].desc}
                    </p>
                  </div>
                  <Screen />
                </div>
              );
            })}
          </div>
        </div>
        <style>{`
            .rp-fill { transform-origin: top left; animation-name: rp-fill; animation-timing-function: linear; animation-fill-mode: forwards; }
            @keyframes rp-fill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
            @media (min-width: 1024px) {
              @keyframes rp-fill { from { transform: scaleY(0); } to { transform: scaleY(1); } }
            }
            @media (prefers-reduced-motion: reduce) { .rp-fill { animation: none; transform: none; } }
          `}</style>

        {/* 마지막: 행동으로 */}
        <div className="mt-14 flex flex-col items-start gap-4 border-t border-white/10 pt-8 sm:mt-24 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:pt-12">
          <div>
            <p className="text-xl font-extrabold text-white sm:text-2xl">
              내 상가는 어떤 답이 나올까요?
            </p>
            <p className="mt-1.5 text-sm text-[#C3CCD8] sm:mt-2 sm:text-15">
              주소만 넣으면 같은 리포트를 받아볼 수 있어요.
            </p>
          </div>
          <Link
            href="/vacancy-input"
            className="inline-flex h-12 items-center gap-2 rounded-full bg-[#2453D6] px-5 text-sm font-bold text-white shadow-[0_12px_28px_rgba(36,83,214,0.4)] sm:h-14 sm:px-7 sm:text-base"
          >
            내 상가로 분석해 보기 <ArrowRight size={18} aria-hidden />
          </Link>
        </div>
      </div>
    </section>
  );
}
