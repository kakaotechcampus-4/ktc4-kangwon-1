'use client';

import {
  createElement,
  useEffect,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import Image from 'next/image';
import Link from 'next/link';
import {
  Menu,
  ChevronRight,
  ArrowUp,
  ArrowDownRight,
  CheckCircle2,
  TriangleAlert,
} from 'lucide-react';
import Header from '@/components/layout/Header';
import SchoolRegulation from '@/components/report/SchoolRegulation';
import SchoolRegulationMap from '@/components/report/SchoolRegulationMap';
import IndustryReview, {
  industrySymbol,
} from '@/components/report/IndustryReview';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import './report.css';
import { mockReportData } from '@/lib/mockData/report';
import { mockProperty } from '@/lib/mockData/property';
import type {
  BusinessLifecycleData,
  CommercialAreaData,
  FloatingPopulationData,
} from '@/lib/mockData/report';
import {
  loadAnalysisResult,
  loadConfirmedBuilding,
  loadVacancyInput,
  type VacancyInput,
} from '@/lib/api/resultStore';
import type { BuildingInfo } from '@/lib/api/building';
import {
  PARKING_LABELS,
  FACILITY_LABELS,
  formatArea,
} from '@/components/building-confirm/labels';
import type {
  AgentAnalysis,
  AgentId,
  DecisionResult,
  IndustryAssessment,
} from '@/lib/api/types';
import { adaptCommercialArea } from '@/lib/api/adapters/commercialArea';
import { adaptBusinessLifecycle } from '@/lib/api/adapters/businessLifecycle';
import { adaptFloatingPopulation } from '@/lib/api/adapters/floatingPopulation';

const chapters = [
  ['space', '상가 정보'],
  ['regulations', '입점 규제 확인'],
  ['conclusion', '핵심 결론'],
  ['compare', '업종 비교'],
  ['customers', '유동인구'],
  ['competition', '경쟁업체'],
  ['lifecycle', '개폐업 추이'],
  ['actions', '다음 할 일'],
] as const;

function Chapter({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="report-chapter scroll-mt-24 pb-16 pt-12"
      style={{ borderColor: colors.neutral.border }}
    >
      <header className="chapter-heading">
        <h2 className="chapter-numbered-title">
          <span className="chapter-number">
            {String(
              chapters.findIndex(([chapterId]) => chapterId === id) + 1
            ).padStart(2, '0')}
          </span>
          <span>
            {chapters.find(([chapterId]) => chapterId === id)?.[1] ?? title}
          </span>
        </h2>
        <p className="chapter-description">
          {id === 'space'
            ? '분석 대상 상가의 기본 정보를 확인하세요.'
            : id === 'conclusion'
              ? '추천 업종과 주요 판단 근거를 확인하세요.'
              : title}
        </p>
      </header>
      <div className="original-report-content">{children}</div>
    </section>
  );
}

const followUpSteps = [
  {
    title: '입점 가능한 업종인지 확인',
    detail:
      '건축물 용도와 학교 주변 규제 내용을 확인하고, 해당 업종의 인허가 조건을 관할 기관에 문의하세요.',
    target: '#regulations',
    link: '입점 규제 보기',
    stage: '먼저 확인',
  },
  {
    title: '설비와 고객 접근 동선 점검',
    detail:
      '급·배수와 전력 용량, 환기·배기 시설을 확인하세요. 엘리베이터, 간판 노출, 주차와 출입 동선도 현장에서 살펴보세요.',
    target: '#space',
    link: '상가 정보 보기',
    stage: '현장 점검',
  },
  {
    title: '실제 수요와 경쟁 점포 확인',
    detail:
      '평일·주말의 주요 시간대에 방문해 통행량과 주변 점포의 가격·고객층을 살펴보고, 리포트의 분석 결과와 비교하세요.',
    target: '#customers',
    link: '상권 분석 보기',
    stage: '현장 점검',
  },
  {
    title: '비용을 계산하고 최종 업종 결정',
    detail:
      '보증금·임대료·관리비와 공사·설비 견적을 정리하세요. 예상 운영비와 필요한 매출을 계산한 뒤 후보 업종을 좁히세요.',
    target: '#compare',
    link: '업종 순위 보기',
    stage: '최종 검토',
  },
];

function ActionChecklist() {
  const [checked, setChecked] = useState<boolean[]>(
    followUpSteps.map(() => false)
  );
  const completed = checked.filter(Boolean).length;
  return (
    <div className="action-plan">
      <div className="action-plan-summary">
        <div>
          <h3>결정 전, 네 가지를 확인하세요</h3>
          <p>리포트의 추천을 현장 조건과 비용까지 연결해 보세요.</p>
        </div>
        <div className="action-plan-progress">
          <span aria-live="polite">
            <strong>{completed}</strong> / {followUpSteps.length} 완료
          </span>
          <progress
            aria-label="확인 항목 완료 현황"
            max={followUpSteps.length}
            value={completed}
          />
        </div>
      </div>
      <ol className="action-plan-list">
        {followUpSteps.map((step, index) => (
          <li key={step.title} className={checked[index] ? 'is-complete' : ''}>
            <span className="action-step-number" aria-hidden="true">
              {String(index + 1).padStart(2, '0')}
            </span>
            <div className="action-step-content">
              <span className="action-step-stage">{step.stage}</span>
              <h4>{step.title}</h4>
              <p>{step.detail}</p>
              <a href={step.target}>
                {step.link}
                <ChevronRight size={16} aria-hidden="true" />
              </a>
            </div>
            <label className="action-step-check">
              <input
                type="checkbox"
                checked={checked[index]}
                aria-label={`${step.title} 완료`}
                onChange={() =>
                  setChecked((previous) =>
                    previous.map((value, i) => (i === index ? !value : value))
                  )
                }
              />
              <span>{checked[index] ? '완료' : '확인 완료'}</span>
            </label>
          </li>
        ))}
      </ol>
      <p className="action-plan-note">
        체크 표시는 현재 화면에서만 유지됩니다.
      </p>
    </div>
  );
}

function MissingData({ label }: { label: string }) {
  return (
    <p
      className="rounded-xl border bg-white p-6 text-lg"
      style={{ borderColor: colors.neutral.border }}
    >
      {label} 데이터를 받아오지 못했습니다. 자료가 확보되면 이곳에 표시합니다.
    </p>
  );
}

function findAgent(
  result: DecisionResult,
  agentId: AgentId
): AgentAnalysis | undefined {
  return result.source_analyses.find((agent) => agent.agent_id === agentId);
}

/**
 * agent.data는 백엔드 계약상 Record<string, unknown>이고, 어떤 필드를
 * 담을지는 각 분석 에이전트가 정한다(backend/app/schemas.py 주석 참고).
 *
 * 세 에이전트(floating_population, commercial_area, business_lifecycle)
 * 모두 default_agents()(backend/app/agents/orchestration/workflow.py)에
 * 등록돼 있어 실호출로 진짜 데이터가 온다. 각자 전용 어댑터
 * (lib/api/adapters/floatingPopulation.ts, commercialArea.ts,
 * businessLifecycle.ts)로 실제 snake_case 출력을 화면 타입으로 옮긴다.
 * status/warnings는 data 안이 아니라 AgentAnalysis 봉투에 있어 envelope
 * 인자로 따로 넘긴다.
 */
function extractFloatingPopulationData(
  agent: AgentAnalysis | undefined
): FloatingPopulationData | null {
  if (!agent) {
    return null;
  }
  return adaptFloatingPopulation(agent.data, {
    status: agent.status,
    warnings: agent.warnings,
    errorMessage: agent.error?.message,
  });
}

function extractCommercialAreaData(
  agent: AgentAnalysis | undefined
): CommercialAreaData | null {
  if (!agent) {
    return null;
  }
  return adaptCommercialArea(agent.data, {
    status: agent.status,
    warnings: agent.warnings,
    errorMessage: agent.error?.message,
  });
}

// 결정 에이전트의 recommendations/not_recommended에서 업종명(category.middle)만
// 뽑는다 — adaptBusinessLifecycle이 개폐업 에이전트의 70여 개 업종 중 이
// 리포트가 다루는 10개만 골라내는 데 쓴다.
function industryNames(items: IndustryAssessment[]): string[] {
  return items.map((item) => item.category.middle);
}

function extractBusinessLifecycleData(
  agent: AgentAnalysis | undefined,
  recommendedNames: string[],
  notRecommendedNames: string[]
): BusinessLifecycleData | null {
  if (!agent || agent.status === 'error') {
    return null;
  }
  return adaptBusinessLifecycle(
    agent.data,
    recommendedNames,
    notRecommendedNames
  );
}

export default function ReportPage() {
  const [active, setActive] = useState<string>('space');
  const [menuOpen, setMenuOpen] = useState(false);
  const [largeText, setLargeText] = useState(false);
  useEffect(() => {
    const update = () => {
      const passed = chapters.filter(
        ([id]) =>
          (document.getElementById(id)?.getBoundingClientRect().top ??
            Infinity) <= 150
      );
      setActive(passed.at(-1)?.[0] ?? 'space');
    };
    window.addEventListener('scroll', update, { passive: true });
    return () => window.removeEventListener('scroll', update);
  }, []);
  const [analysisResult, setAnalysisResult] = useState<DecisionResult | null>(
    null
  );
  // 앞 단계(주소 입력·상가 정보 확인)에서 받은 값. mock 모드처럼 분석 결과가
  // 없을 때도 리포트 머리말이 입력한 상가를 가리키게 한다.
  const [vacancyInput, setVacancyInput] = useState<VacancyInput | null>(null);
  const [building, setBuilding] = useState<BuildingInfo | null>(null);

  useEffect(() => {
    // sessionStorage는 브라우저 전용이라 서버 렌더에서는 접근할 수 없다.
    // 마운트 후 한 번만 읽어 온다 — 이 첫 렌더 이후의 추가 렌더 한 번은
    // 페이지 진입 시 결과를 채워 넣는 데 불가피하다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnalysisResult(loadAnalysisResult());
    setVacancyInput(loadVacancyInput());
    setBuilding(loadConfirmedBuilding());
  }, []);

  const floatingPopulationData = analysisResult
    ? extractFloatingPopulationData(
        findAgent(analysisResult, 'floating_population')
      )
    : undefined;
  const competitorData = analysisResult
    ? extractCommercialAreaData(findAgent(analysisResult, 'commercial_area'))
    : undefined;
  const businessLifecycleData = analysisResult
    ? extractBusinessLifecycleData(
        findAgent(analysisResult, 'business_lifecycle'),
        industryNames(analysisResult.recommendations),
        industryNames(analysisResult.not_recommended)
      )
    : undefined;

  const analyzedDate = analysisResult
    ? new Date().toLocaleDateString('ko-KR')
    : mockReportData.analyzedDate;
  const inputAddress = vacancyInput
    ? [vacancyInput.roadAddress, vacancyInput.floorUnit.trim()]
        .filter(Boolean)
        .join(' ')
    : undefined;
  const headerAddress = analysisResult?.address ?? inputAddress;
  const address = headerAddress ?? mockReportData.address;
  const displayAddress = address.replace(/\s+\d+층(?:\s+\d+호)?$/, '');
  const parkingValue = building?.parking.value;
  const areaValue = building?.exclusiveAreaM2.value;
  const facilityValue = building?.facility.value;
  const isPropertyPreview = !vacancyInput && !analysisResult && !building;
  const facilityLabel = facilityValue
    ? FACILITY_LABELS[facilityValue]
    : isPropertyPreview
      ? mockProperty.facility
      : '조회 필요';
  const sewageLabel =
    building?.sewage.value ??
    (isPropertyPreview ? mockProperty.sewage : '조회 필요');
  const radiusText = vacancyInput?.radius.trim();
  const radiusValue = radiusText ? Number(radiusText) : undefined;
  // 미리보기는 디자인 기준인 100m를 쓰고, 실제 보고서의 누락된 입력은 명시합니다.
  const radiusLabel =
    radiusValue !== undefined &&
    Number.isInteger(radiusValue) &&
    radiusValue > 0
      ? `${radiusValue.toLocaleString('ko-KR')}m`
      : !vacancyInput && !analysisResult
        ? '100m'
        : '미입력';

  const top = analysisResult?.recommendations[0];
  const topName = analysisResult
    ? top?.category.middle
    : mockReportData.recommended[0]?.name;
  const TopSymbol = industrySymbol(topName ?? '');
  const summaryText =
    analysisResult?.summary ??
    mockReportData.aiAnalysisSummary.recommendationReason;
  const primaryReasons = analysisResult
    ? (top?.reasons ?? [])
    : (mockReportData.recommended[0]?.tags ?? []);
  const navigation = (
    <nav aria-label="리포트 목차" className="flex flex-col gap-1">
      {chapters.map(([id, label], index) => (
        <a
          key={id}
          href={`#${id}`}
          onClick={() => setMenuOpen(false)}
          aria-current={active === id ? 'location' : undefined}
          className="flex min-h-12 items-center gap-3 rounded-xl px-4 py-3 text-base"
          style={{
            color: active === id ? reportPalette.navy : colors.text.secondary,
            backgroundColor:
              active === id ? `${reportPalette.brand}12` : 'transparent',
            fontWeight: active === id ? 700 : 400,
          }}
        >
          <span className="toc-number">
            {String(index + 1).padStart(2, '0')}
          </span>
          <span>{label}</span>
          {active === id && (
            <ChevronRight
              size={18}
              className="ml-auto shrink-0"
              aria-hidden="true"
            />
          )}
        </a>
      ))}
    </nav>
  );
  return (
    <div
      className="min-h-screen"
      style={
        {
          backgroundColor: reportPalette.canvas,
          color: reportPalette.ink,
          '--rp-navy': reportPalette.navy,
          '--rp-blue': reportPalette.brand,
          '--rp-amber': reportPalette.amber,
          '--rp-amber-wash': reportPalette.amberWash,
        } as CSSProperties
      }
    >
      <Header />
      <div
        className="report-page mx-auto max-w-[1360px] px-5 pb-20 pt-0 sm:px-8"
        style={{ '--font-scale': largeText ? 1.2 : 1 } as CSSProperties}
      >
        <div className="report-intro">
          <div className="report-top-actions mb-6 flex flex-wrap items-center justify-between gap-4">
            <Link
              href="/"
              className="inline-flex min-h-11 items-center text-sm"
            >
              ← 리포트 목록 보기
            </Link>
            <button
              type="button"
              aria-pressed={largeText}
              onClick={() => setLargeText((v) => !v)}
              className="inline-flex h-11 shrink-0 items-center rounded-md border bg-white px-4 text-sm font-semibold"
              style={{ borderColor: colors.neutral.border }}
            >
              <span className="mr-2 text-[#006b65]" aria-hidden="true">
                Aa
              </span>
              {largeText ? '기본 글씨로 보기' : '글씨 크게 보기'}
            </button>
          </div>
          <header className="report-masthead">
            <div>
              <p className="report-masthead-eyebrow">상가 분석</p>
              <h1 className="report-cover-title text-[34px] font-bold leading-snug sm:text-[44px]">
                상가 업종 분석 리포트
              </h1>
            </div>
            <div className="report-masthead-date">
              <span>분석일</span>
              <p>{analyzedDate}</p>
            </div>
          </header>
        </div>
        <div
          className="sticky top-0 z-20 mb-4 border-y bg-white lg:hidden"
          style={{ borderColor: colors.neutral.border }}
        >
          <button
            type="button"
            aria-expanded={menuOpen}
            aria-controls="mobile-report-menu"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex min-h-14 w-full items-center justify-between px-4 text-base font-semibold"
          >
            <span>{chapters.find((item) => item[0] === active)?.[1]}</span>
            <span className="flex items-center gap-2">
              <Menu size={18} />
              목차 보기
            </span>
          </button>
          {menuOpen && (
            <div
              id="mobile-report-menu"
              className="max-h-[60vh] overflow-auto p-2"
            >
              {navigation}
            </div>
          )}
        </div>
        <div
          className="grid items-start gap-8 lg:grid-cols-[190px_minmax(0,1fr)]"
          style={{ borderColor: reportPalette.navy }}
        >
          <aside className="report-toc sticky top-8 hidden pt-12 lg:block">
            <div className="mb-5 flex items-center justify-between px-3">
              <p className="text-base font-semibold">리포트 목차</p>
              <span className="text-sm text-gray-500">
                {String(
                  chapters.findIndex(([id]) => id === active) + 1
                ).padStart(2, '0')}{' '}
                / {String(chapters.length).padStart(2, '0')}
              </span>
            </div>
            {navigation}
          </aside>
          <main className="min-w-0">
            <Chapter
              id="space"

              title="분석할 상가 정보"
            >
              <header className="property-card-address">
                <p className="property-address-label">분석 대상 주소</p>
                <h3 className="property-address">{displayAddress}</h3>
              </header>
              <div className="property-photo-layout">
                <figure className="property-preview-photo">
                  <Image
                    src="/images/property-interior-example.png"
                    alt="큰 창이 있는 빈 상가 내부"
                    fill
                    sizes="(max-width: 900px) 100vw, 40vw"
                    className="object-cover"
                  />
                </figure>
                <div className="property-preview-info">
                  <dl className="property-facts property-main-facts">
                    <div>
                      <dt>전용면적</dt>
                      <dd>
                        {/* 실제 흐름에서 값이 없으면 목업 대신 "조회 필요"로 둔다.
                            목업 값은 입력·결과가 전혀 없는 미리보기에서만 쓴다. */}
                        {areaValue !== null && areaValue !== undefined
                          ? formatArea(areaValue)
                          : isPropertyPreview
                            ? mockReportData.area.replace(/^전용\s*/, '')
                            : '조회 필요'}
                        {(isPropertyPreview ||
                          (areaValue !== null && areaValue !== undefined)) && (
                          <span className="property-fact-note">
                            (약{' '}
                            {areaValue !== null && areaValue !== undefined
                              ? (Number(areaValue) / 3.305785).toFixed(1)
                              : '83.3'}
                            평)
                          </span>
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>층 / 호수</dt>
                      <dd>
                        {vacancyInput?.floorUnit.trim() ||
                          (isPropertyPreview ? mockReportData.floor : '미입력')}
                      </dd>
                    </div>
                  </dl>
                  <div className="property-facilities">
                    <dl className="property-facts">
                      <div>
                        <dt>근린생활시설</dt>
                        <dd>{facilityLabel}</dd>
                      </div>
                      <div>
                        <dt>오수정화시설</dt>
                        <dd>{sewageLabel}</dd>
                      </div>
                    </dl>
                  </div>
                  <dl className="property-facts property-radius-row">
                    <div>
                      <dt>주차 가능 여부</dt>
                      <dd>
                        {parkingValue ? PARKING_LABELS[parkingValue] : '모름'}
                      </dd>
                    </div>
                    <div className="property-analysis-range">
                      <dt>분석 범위</dt>
                      <dd>
                        <strong>{radiusLabel}</strong>
                        <span className="property-fact-note">
                          (상가 중심 반경)
                        </span>
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </Chapter>
            <Chapter
              id="regulations"
              title="추천 업종보다 먼저, 입점 규제를 확인하세요"
            >
              <SchoolRegulation>
                <SchoolRegulationMap embedded />
              </SchoolRegulation>
            </Chapter>
            <Chapter id="conclusion" title="이 상가의 핵심 결론">
              <div className="conclusion-lead">
                <p className="conclusion-lead-label">검토 방향</p>
                <p>
                  {analysisResult
                    ? summaryText
                    : `${topName}를 우선 검토하되, 4층 접근성과 급·배수 조건을 확인하세요.`}
                </p>
              </div>
              <div className="decision-cover">
                <div className="recommended-focus">
                  <p>가장 먼저 검토할 업종</p>
                  <div className="industry-identity">
                    <div className="cover-industry-icon">
                      {createElement(TopSymbol, {
                        size: 44,
                        strokeWidth: 1.6,
                        'aria-hidden': true,
                      })}
                    </div>
                    <h3>{topName ?? '추천 결과 없음'}</h3>
                  </div>
                  <div className="recommendation-footer">
                    <a href="#compare">
                      업종 순위 보러가기 <ArrowDownRight size={20} />
                    </a>
                    {(top?.score ??
                      (!analysisResult
                        ? mockReportData.recommended[0]?.score
                        : undefined)) !== undefined && (
                      <p className="cover-score">
                        <strong>
                          {top?.score ?? mockReportData.recommended[0]?.score}점
                        </strong>
                        <span>업종 적합도</span>
                      </p>
                    )}
                  </div>
                </div>
                <div className="key-evidence">
                  <h3>이 업종을 추천하는 이유</h3>
                  <ul>
                    {primaryReasons.map((reason, i) => (
                      <li key={i}>
                        <CheckCircle2 size={23} aria-hidden="true" />
                        <span>{reason}</span>
                        <a
                          className="evidence-detail-link"
                          href={
                            /폐업|개업|증가|감소|추이/.test(reason)
                              ? '#lifecycle'
                              : /인구|연령|통행/.test(reason)
                                ? '#customers'
                                : '#competition'
                          }
                          aria-label={`${reason} 분석 근거 보기`}
                        >
                          근거 보기 <ChevronRight size={14} />
                        </a>
                      </li>
                    ))}
                  </ul>
                  {primaryReasons.length === 0 && (
                    <p>제공된 추천 근거가 없습니다.</p>
                  )}
                </div>
              </div>
              <div className="conclusion-checks">
                <div className="entry-heading">
                  <TriangleAlert size={22} aria-hidden="true" />
                  <h3>입점 전 확인할 사항</h3>
                </div>
                {analysisResult ? (
                  top?.risks?.length ? (
                    <ul>
                      {top.risks.map((text, i) => (
                        <li key={i}>{text}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>
                      분석 결과에 별도 조건이 기재되지 않았습니다. 현장에서 입점
                      조건을 확인하세요.
                    </p>
                  )
                ) : (
                  <div className="conclusion-check-grid">
                    <div>
                      <h4>접근성과 노출</h4>
                      <p>4층까지의 엘리베이터 동선과 간판 노출을 확인하세요.</p>
                    </div>
                    <div>
                      <h4>설비와 공사 조건</h4>
                      <p>급·배수, 전력 용량과 공사 허용 범위를 확인하세요.</p>
                    </div>
                    <div>
                      <h4>입점 규제</h4>
                      <p>
                        학교 주변 보호구역과 대상 업종의 제한 여부를 확인하세요.
                      </p>
                      <a href="#regulations">
                        규제 확인하기 <ChevronRight size={14} />
                      </a>
                    </div>
                  </div>
                )}
              </div>
            </Chapter>
            <Chapter
              id="compare"

              title="이 상가에 맞는 업종 순위"
            >
              <IndustryReview
                recommendations={analysisResult?.recommendations}
                notRecommended={analysisResult?.not_recommended}
              />
            </Chapter>
            <Chapter
              id="customers"

              title="주변에는 어떤 사람들이 오갈까요?"
            >
              {analysisResult && !floatingPopulationData ? (
                <MissingData label="유동인구" />
              ) : (
                <FloatingPopulationSection
                  reportLayout
                  compactReference
                  data={floatingPopulationData ?? undefined}
                />
              )}
            </Chapter>
            <Chapter
              id="competition"

              title="같은 업종은 얼마나 있을까요?"
            >
              {analysisResult && !competitorData ? (
                <MissingData label="경쟁업체" />
              ) : (
                <CompetitorAnalysisSection
                  reportLayout
                  data={competitorData ?? undefined}
                  recommendations={analysisResult?.recommendations}
                  notRecommended={analysisResult?.not_recommended}
                />
              )}
            </Chapter>
            <Chapter
              id="lifecycle"

              title="새로 열고, 문을 닫는 흐름은?"
            >
              {analysisResult && !businessLifecycleData ? (
                <MissingData label="개폐업" />
              ) : (
                <OpenCloseTrendSection
                  reportLayout
                  compactReference
                  data={businessLifecycleData ?? undefined}
                />
              )}
            </Chapter>
            <Chapter id="actions" title="리포트를 읽은 뒤 확인할 일">
              <ActionChecklist />
              {top?.risks?.length ? (
                <div className="mt-6 rounded-xl bg-white p-6">
                  <h3 className="mb-3 text-xl font-semibold">
                    우선 검토 업종의 주의사항
                  </h3>
                  <ul className="list-disc space-y-3 pl-5 text-lg">
                    {top.risks.map((risk, i) => (
                      <li key={i}>{risk}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <a
                href="#conclusion"
                className="mt-7 inline-flex min-h-12 items-center gap-2 rounded-xl border bg-white px-5 text-base font-semibold"
                style={{ borderColor: colors.neutral.border }}
              >
                <ArrowUp size={17} />
                핵심 결론 다시 보기
              </a>
            </Chapter>
          </main>
        </div>
      </div>
    </div>
  );
}
