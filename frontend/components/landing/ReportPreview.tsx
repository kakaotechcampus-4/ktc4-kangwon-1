'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { ArrowRight, Building2, FileText, TriangleAlert } from 'lucide-react';
import { mockReportData } from '@/lib/mockData/report';

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
    <div className="overflow-hidden rounded-[20px] bg-white shadow-[0_30px_60px_rgba(0,0,0,0.28)]">
      <div className="flex items-center justify-between gap-3 border-b border-[#EEF1F5] bg-[#F3F6FA] px-5 py-3">
        <span className="flex items-center gap-2">
          <FileText size={16} className="text-[#2453D6]" aria-hidden />
          <span className="text-13 font-extrabold text-[#10233A]">
            채움 분석 리포트
          </span>
          <span className="rounded bg-[#10233A] px-1.5 py-0.5 text-[11px] font-bold text-white">
            예시
          </span>
        </span>
        <span className="text-xs font-bold text-[#2453D6]">{caption}</span>
      </div>
      {children}
    </div>
  );
}

function AnswerScreen() {
  return (
    <Frame caption="02 핵심 결론">
      <div
        className="relative px-6 py-6 text-white"
        style={{
          background: [
            'radial-gradient(60% 90% at 90% 0%, rgba(46,82,190,0.42) 0%, rgba(46,82,190,0) 60%)',
            'linear-gradient(135deg, #0F1D45 0%, #0A1631 100%)',
          ].join(','),
        }}
      >
        <p className="flex items-center gap-1.5 text-13 font-bold text-[#9FB4D6]">
          <Building2 size={15} aria-hidden /> 가장 먼저 검토할 업종
        </p>
        <p className="mt-2 text-2xl font-extrabold tracking-[-0.03em]">
          {top3[0].name}
        </p>
        <span className="mt-2 inline-flex rounded-full bg-[#FFCF7A] px-2.5 py-0.5 text-13 font-bold text-[#10233A]">
          조건부 추천
        </span>
        <p className="mt-4 text-base leading-[1.6] font-bold">
          {top3[0].name}를 먼저 검토하되,{' '}
          <span className="text-[#FFCF7A]">아래 2가지를 직접 확인한 뒤</span>{' '}
          결정하세요.
        </p>
        <span
          aria-hidden
          className="absolute bottom-0 left-[calc(1.5rem+9px)] h-6 border-l-2 border-dashed border-[#FFCF7A]/70"
        />
      </div>
      <div className="px-6 pb-6">
        <span
          aria-hidden
          className="ml-[9px] block h-4 border-l-2 border-dashed border-[#E2B45C]/70"
        />
        <p className="flex items-center gap-1.5 text-base font-extrabold text-[#10233A]">
          <TriangleAlert size={18} color="#A65B00" aria-hidden />
          계약 전에 확인할 2가지
        </p>
        <ol className="mt-3 flex flex-col gap-3">
          {[
            [
              '4층까지 드나들기 쉬운지와 간판 노출',
              '엘리베이터 동선과 간판 위치를 현장에서 확인하세요.',
            ],
            [
              '실제로 쓸 수 있는 면적',
              '넓은 공간을 나눠 쓸 수 있는지 도면으로 확인하세요.',
            ],
          ].map(([t, d], i) => (
            <li key={t} className="grid grid-cols-[32px_1fr] gap-x-2">
              <span className="text-lg leading-none font-extrabold text-[#2453D6]">
                0{i + 1}
              </span>
              <div>
                <p className="text-15 font-bold text-[#10233A]">{t}</p>
                <p className="text-13 leading-5 text-[#4B5866]">{d}</p>
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

const AGES: [string, number, number][] = [
  // 연령대, 구성비(%), 서울 평균 대비(배)
  ['20대', 15, 0.62],
  ['30대', 17, 0.71],
  ['40대', 24, 1.18],
  ['50대', 22, 1.55],
  ['60대+', 17, 1.42],
];

const COMPETITION: [string, number | null, number | null, boolean][] = [
  // 업종, 동종 점포 수, 반경 2,000m 대비(배), 추천 업종
  ['네일·뷰티', 1, 0.82, true],
  ['소형 스튜디오', 2, 1.35, true],
  ['코인세탁실', 3, 0.65, true],
  ['대형 카페', 12, 1.62, false],
];

function Ratio({ value }: { value: number }) {
  const up = value > 1;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-xs font-bold tabular-nums"
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
      <div className="flex flex-col gap-5 px-6 py-5">
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
              className="flex-1 rounded-full py-2 text-13 font-bold transition-colors"
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
          <div className="flex flex-col gap-4">
            {/* 리포트 05장과 같은 상권 유형 일러스트(주거생활형) */}
            <div className="flex items-center justify-between gap-4">
              <p className="text-lg leading-snug font-extrabold text-[#10233A]">
                이 주변은
                <br />
                <span className="text-[#2453D6]">주거생활형</span> 상권이에요
              </p>
              <Image
                src="/images/area-types/residential.webp"
                alt="주거생활형 상권 일러스트"
                width={720}
                height={427}
                className="h-auto w-[150px] shrink-0 sm:w-[170px]"
              />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div className="rounded-xl bg-[#10233A] px-4 py-3 text-white">
                <p className="text-xs font-semibold text-[#9FB4D6]">
                  하루 평균 유동인구
                </p>
                <p className="mt-1 text-2xl font-extrabold">
                  4,820<span className="ml-0.5 text-sm font-bold">명/일</span>
                </p>
              </div>
              <div className="rounded-xl border border-[#E3E9F0] px-4 py-3">
                <p className="text-xs font-semibold text-[#66758A]">
                  가장 많은 연령대
                </p>
                <p className="mt-1 text-2xl font-extrabold text-[#10233A]">
                  40대<span className="ml-1 text-sm font-bold">24%</span>
                </p>
              </div>
            </div>
            <ul className="flex flex-col gap-1.5">
              {AGES.map(([age, pct, idx]) => (
                <li
                  key={age}
                  className="grid grid-cols-[44px_1fr_44px_60px] items-center gap-2 text-xs"
                >
                  <span className="font-bold text-[#10233A]">{age}</span>
                  <span className="h-1.5 rounded-full bg-[#EEF2F6]">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${(pct / 30) * 100}%`,
                        background: age === '40대' ? '#10233A' : '#8DA2C4',
                      }}
                    />
                  </span>
                  <span className="text-right font-semibold tabular-nums text-[#4B5866]">
                    {pct}%
                  </span>
                  <span
                    className="text-right font-bold tabular-nums"
                    style={{ color: idx > 1 ? '#2453D6' : '#8A97A5' }}
                  >
                    {idx.toFixed(2)}배
                  </span>
                </li>
              ))}
            </ul>
            <p className="-mt-1 text-[11px] text-[#8A97A5]">
              구성비 · 서울 평균 대비
            </p>
          </div>
        )}

        {tab === '경쟁 업체' && (
          <div className="flex flex-col gap-4">
            <p className="text-lg leading-snug font-extrabold text-[#10233A]">
              <span className="text-[#2453D6]">네일·뷰티, 코인세탁실</span>은
              주변에 같은 업종이 적고,
              <br />
              <span className="text-[#C2410C]">소형 스튜디오</span>는 이미 몰려
              있어요.
            </p>
            <table className="w-full text-13">
              <thead>
                <tr className="text-xs text-[#8A97A5]">
                  <th className="pb-2 text-left font-semibold">업종</th>
                  <th className="pb-2 text-right font-semibold">동종 점포</th>
                  <th className="pb-2 text-right font-semibold">
                    반경 2km 대비
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPETITION.map(([name, count, ratio, rec]) => (
                  <tr key={name} className="border-t border-[#EEF1F5]">
                    <td
                      className={`py-2 ${rec ? 'font-bold text-[#10233A]' : 'text-[#66758A]'}`}
                    >
                      {name}
                      {!rec && (
                        <span className="ml-1.5 text-[11px] text-[#8A97A5]">
                          제외 후보
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right tabular-nums text-[#4B5866]">
                      {count}개
                    </td>
                    <td className="py-2 text-right">
                      {ratio !== null && <Ratio value={ratio} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === '개폐업' && (
          <div className="flex flex-col gap-4">
            <p className="text-lg leading-snug font-extrabold text-[#10233A]">
              네일·뷰티는 개업이 활발하고
              <br />
              폐업률도 낮아 <span className="text-[#2453D6]">안정적</span>이에요
            </p>
            <div className="flex items-center gap-5">
              <div className="relative h-[72px] w-[124px] shrink-0">
                <svg viewBox="0 0 124 72" className="h-full w-full" aria-hidden>
                  <path
                    d="M10 66 A52 52 0 0 1 114 66"
                    fill="none"
                    stroke="#E3E9F0"
                    strokeWidth="10"
                    strokeLinecap="round"
                  />
                  <path
                    d="M10 66 A52 52 0 0 1 114 66"
                    fill="none"
                    stroke="#2453D6"
                    strokeWidth="10"
                    strokeLinecap="round"
                    pathLength={100}
                    strokeDasharray="78.4 100"
                  />
                </svg>
                <p className="absolute inset-x-0 bottom-0 text-center text-2xl font-extrabold text-[#10233A]">
                  78.4
                </p>
              </div>
              <div className="flex flex-col gap-1.5 text-13 text-[#3D4A5C]">
                <p className="font-bold text-[#10233A]">
                  개폐업 안정성 78.4 / 100점
                </p>
                <p>최근 1년 폐업률 7.4% — 과거(15.8%)보다 하락</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 rounded-xl bg-[#F5F8FB] p-3 text-center">
              <div>
                <p className="text-xs text-[#66758A]">3년 개업</p>
                <p className="text-lg font-extrabold text-[#2453D6]">20</p>
              </div>
              <div>
                <p className="text-xs text-[#66758A]">3년 폐업</p>
                <p className="text-lg font-extrabold text-[#C2410C]">9</p>
              </div>
              <div>
                <p className="text-xs text-[#66758A]">순증감</p>
                <p className="text-lg font-extrabold text-[#10233A]">▲ +11</p>
              </div>
            </div>
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
      <div className="flex flex-col gap-5 px-6 py-6">
        <div>
          <span className="block h-8 font-serif text-[56px] leading-none font-black text-[#F0A43A]">
            &ldquo;
          </span>
          <p className="text-lg leading-[1.45] font-extrabold tracking-[-0.02em] text-[#10233A]">
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
                  className="inline-flex size-11 overflow-hidden rounded-full bg-white"
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
                <span className="mt-1 text-xs font-bold whitespace-nowrap text-[#10233A]">
                  {r.name}
                </span>
                <span
                  className="text-[11px] font-semibold whitespace-nowrap"
                  style={{ color: r.t }}
                >
                  {r.v}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="rounded-xl bg-[#EAF0F6] px-4 py-3 text-13 leading-5 text-[#3D4A5C]">
          <b className="text-[#10233A]">임대인 대변인</b> · 임대료와 공실 기간
          자료가 없어 수익은 따로 확인해야 한다고 봤어요.
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
      className="relative w-full scroll-mt-16 px-5 py-24 sm:px-8"
      style={{ backgroundColor: '#10233A' }}
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="flex flex-col items-start">
          <p className="text-sm font-bold tracking-[0.08em] text-[#9DB5F2]">
            REPORT PREVIEW
          </p>
          <h2 className="mt-3.5 flex flex-wrap items-center gap-3 text-3xl leading-[1.3] font-extrabold tracking-[-0.02em] text-white sm:text-4xl">
            분석 리포트 미리보기
            <span className="rounded-md bg-[#FFCF7A] px-2.5 py-1 text-sm font-extrabold tracking-normal text-[#10233A] sm:text-base">
              예시 리포트
            </span>
          </h2>
        </div>

        {/* 한 화면에 고정된 무대 — 3초마다 다음 단계가 아래에서 위로 올라온다 */}
        <div
          ref={stageRef}
          className="mt-14 grid gap-10 lg:grid-cols-[56px_minmax(0,1fr)] lg:gap-8"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
        >
          {/* 단계 표시 — 진행 막대가 차오르고, 눌러서 바로 이동할 수도 있다 */}
          <ol className="flex gap-3 lg:flex-col lg:gap-4 lg:pt-2">
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
                    <span className="relative h-1 w-full overflow-hidden rounded-full bg-white/10 lg:h-20 lg:w-1">
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
                  className="col-start-1 row-start-1 grid items-center gap-8 transition-[opacity,transform] duration-700 ease-[cubic-bezier(0.2,0.7,0.2,1)] motion-reduce:transition-none lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16"
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
                    <span className="rounded-full bg-[#FFCF7A] px-3 py-1 text-sm font-bold text-[#10233A]">
                      {i + 1} · {STEPS[i].label}
                    </span>
                    <p className="mt-5 text-2xl leading-[1.4] font-extrabold whitespace-pre-line text-white sm:text-3xl">
                      {STEPS[i].title}
                    </p>
                    <p className="mt-3 max-w-[420px] text-base leading-7 text-[#C3CCD8]">
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
        <div className="mt-24 flex flex-col items-start gap-6 border-t border-white/10 pt-12 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-2xl font-extrabold text-white">
              내 상가는 어떤 답이 나올까요?
            </p>
            <p className="mt-2 text-15 text-[#C3CCD8]">
              주소만 넣으면 같은 리포트를 받아볼 수 있어요.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/vacancy-input"
              className="inline-flex h-14 items-center gap-2 rounded-full bg-[#2453D6] px-7 text-base font-bold text-white shadow-[0_12px_28px_rgba(36,83,214,0.4)]"
            >
              내 상가로 분석해 보기 <ArrowRight size={18} aria-hidden />
            </Link>
            <Link
              href="/report"
              className="inline-flex h-14 items-center rounded-full border border-white/30 px-6 text-base font-bold text-white/90 hover:bg-white/10"
            >
              예시 리포트 전체 보기
            </Link>
          </div>
        </div>
        <p className="mt-6 text-xs text-[#8EA0BA]">
          * 실제 분석 데이터가 아닌, 리포트 구성을 보여주는 예시예요.
        </p>
      </div>
    </section>
  );
}
