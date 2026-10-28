'use client';

import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import {
  Menu,
  ChevronRight,
  ArrowDownRight,
  TriangleAlert,
  MapPin,
  Building2,
} from 'lucide-react';
import Header from '@/components/layout/Header';
import PropertyMap from '@/components/report/PropertyMap';
import IndustryReview, {
  candidateChecks,
} from '@/components/report/IndustryReview';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import {
  FactCompetitionSection,
  FactFloatingPopulationSection,
  FactLifecycleSection,
} from '@/components/report/FactSections';
import EvaluatorReviews from '@/components/report/EvaluatorReviews';
import TenantMatchingProposal from '@/components/report/TenantMatchingProposal';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import './report.css';
import { mockReportData } from '@/lib/mockData/report';
import { mockProperty } from '@/lib/mockData/property';
import {
  loadAnalysisResult,
  loadAnalysisFacts,
  loadRequestId,
  saveAnalysisFacts,
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
import type { DecisionResult, FactView } from '@/lib/api/types';
import { getAnalysisFacts } from '@/lib/api/analyses';
import { indexFacts, renderSegments } from '@/lib/api/segments';
import {
  competitionFromFacts,
  floatingPopulationFromFacts,
  lifecycleFromFacts,
} from '@/lib/api/adapters/facts';

// 장 제목 위 영문 라벨 — 랜딩 섹션 라벨과 같은 형식
const chapterEyebrows: Record<string, string> = {
  space: 'SPACE',
  conclusion: 'CONCLUSION',
  compare: 'COMPARE',
  reviews: 'CROSS REVIEW',
  customers: 'FOOT TRAFFIC',
  competition: 'COMPETITION',
  lifecycle: 'OPEN · CLOSE',
  listing: 'NEXT STEP',
};

const chapters = [
  ['space', '상가 정보'],
  ['conclusion', '핵심 결론'],
  ['compare', '업종 비교'],
  ['reviews', '교차 검토'],
  ['customers', '유동인구'],
  ['competition', '경쟁업체'],
  ['lifecycle', '개폐업 추이'],
  ['listing', '임차인 찾기'],
] as const;

function Chapter({
  id,
  title,
  aside,
  screenOnly = false,
  children,
}: {
  id: string;
  title: string;
  // 설명 문장과 같은 줄 오른쪽에 붙는 보조 정보
  aside?: ReactNode;
  screenOnly?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={`report-chapter scroll-mt-24 pb-16 pt-12${screenOnly ? ' report-screen-only' : ''}`}
      style={{ borderColor: colors.neutral.border }}
    >
      <header className="chapter-heading">
        <p className="chapter-eyebrow">
          {String(
            chapters.findIndex(([chapterId]) => chapterId === id) + 1
          ).padStart(2, '0')}
          {chapterEyebrows[id] ? ` · ${chapterEyebrows[id]}` : ''}
        </p>
        <h2 className="chapter-numbered-title">
          <span>
            {chapters.find(([chapterId]) => chapterId === id)?.[1] ?? title}
          </span>
        </h2>
        <div className="chapter-description-row">
          <p className="chapter-description">
            {id === 'space'
              ? '분석 대상 상가의 기본 정보를 확인하세요.'
              : id === 'conclusion'
                ? '추천 업종과 주요 판단 근거를 확인하세요.'
                : id === 'listing'
                  ? '추천 업종을 바탕으로 실제 임차인을 찾아보세요.'
                  : title}
          </p>
          {aside && <span className="chapter-aside">{aside}</span>}
        </div>
      </header>
      <div
        className={`original-report-content${id === 'space' ? ' space-info-content' : ''}`}
      >
        {children}
      </div>
    </section>
  );
}

// loading: 받는 중, failed: 서버에서 받지 못함, empty: 받았지만 이 위치에 자료가 없음
type FactsState = 'loading' | 'failed' | 'empty';

function MissingData({
  label,
  state,
  onRetry,
}: {
  label: string;
  state: FactsState;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white p-6 text-lg"
      style={{ borderColor: colors.neutral.border }}
    >
      <p>
        {state === 'loading'
          ? `${label} 자료를 불러오고 있습니다.`
          : state === 'failed'
            ? `서버에 연결하지 못해 ${label} 자료를 불러오지 못했습니다.`
            : `이 위치에서는 ${label} 자료를 찾지 못했습니다.`}
      </p>
      {state === 'failed' && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 shrink-0 rounded-lg border px-4 text-base font-semibold"
          style={{ borderColor: colors.neutral.border }}
        >
          다시 불러오기
        </button>
      )}
    </div>
  );
}

/** 문장 속 추천 업종 이름을 파란 강조로 감싼다. */
function highlightName(text: string, name?: string | null) {
  if (!name || !text.includes(name)) return text;
  return text.split(name).flatMap((part, i) =>
    i === 0
      ? [part]
      : [
          <em key={i} className="dcs-highlight">
            {name}
          </em>,
          part,
        ]
  );
}

/** 근거 문장이 어느 분석에서 왔는지 한 줄로 알려 준다(근거 보기 링크 대상과 같은 기준). */
function reasonDescription(reason: string, target: string) {
  if (target === '#lifecycle') {
    return /폐업|개업/.test(reason)
      ? '최근 업종 운영 흐름을 검토했습니다.'
      : '업종 점포 수의 장기 변화를 살펴봤습니다.';
  }
  if (target === '#customers') return '주변 유동인구 구성을 함께 살펴봤습니다.';
  return '주변 경쟁 점포 수를 함께 고려했습니다.';
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

  // 차트용 전체 fact. 결과의 facts는 보고서가 인용한 것만 담아 따로 받는다.
  // undefined = 받는 중, null = 받지 못함
  const [allFacts, setAllFacts] = useState<FactView[] | null | undefined>();
  // "다시 불러오기"를 누를 때마다 바뀌어 조회를 다시 시작한다.
  const [factsAttempt, setFactsAttempt] = useState(0);
  useEffect(() => {
    if (!analysisResult) {
      return;
    }
    const requestId = loadRequestId() ?? analysisResult.request_id;
    // 이미 받아 둔 fact가 있으면 서버를 다시 부르지 않는다.
    const saved = loadAnalysisFacts(requestId);
    if (saved) {
      // sessionStorage는 브라우저 전용이라 마운트 후에 읽는다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAllFacts(saved);
      return;
    }
    let cancelled = false;
    setAllFacts(undefined);
    getAnalysisFacts(requestId)
      .then((page) => {
        if (cancelled) return;
        // 자료 조회 전이면 빈 목록이 온다 — 저장하지 않고 다음에 다시 받는다.
        if (page.facts.length) saveAnalysisFacts(requestId, page.facts);
        setAllFacts(page.facts);
      })
      .catch((error: unknown) => {
        // 화면에서 실패를 안내하므로 개발 모드 오류 표시는 띄우지 않는다.
        console.warn('[ReportPage] 차트 자료 조회 실패:', error);
        if (!cancelled) setAllFacts(null);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisResult, factsAttempt]);
  const factsState: FactsState =
    allFacts === undefined ? 'loading' : allFacts === null ? 'failed' : 'empty';
  const retryFacts = () => setFactsAttempt((attempt) => attempt + 1);

  // 문장 속 fact는 결과의 인용 fact로 충분하지만, 전체 fact가 오면 함께 찾는다.
  const factIndex = indexFacts([
    ...(allFacts ?? []),
    ...(analysisResult?.facts ?? []),
  ]);
  const candidateCodes = analysisResult
    ? [
        ...analysisResult.top5.map((item) => item.industry_code),
        ...analysisResult.excluded_candidates.map((item) => item.industry_code),
      ]
    : [];
  const floatingPopulationData = allFacts
    ? floatingPopulationFromFacts(allFacts)
    : null;
  const competitorData = allFacts
    ? competitionFromFacts(allFacts, candidateCodes)
    : null;
  const businessLifecycleData = allFacts
    ? lifecycleFromFacts(allFacts, candidateCodes)
    : null;

  const analyzedDate = analysisResult
    ? new Date().toLocaleDateString('ko-KR')
    : mockReportData.analyzedDate;
  const inputAddress = vacancyInput
    ? [vacancyInput.roadAddress, vacancyInput.floorUnit.trim()]
        .filter(Boolean)
        .join(' ')
    : undefined;
  const address = inputAddress ?? mockReportData.address;
  const displayAddress = address.replace(/\s+\d+층(?:\s+\d+호)?$/, '');
  const parkingValue = building?.parking.value;
  const areaValue = building?.exclusiveAreaM2.value;
  const isPropertyPreview = !vacancyInput && !analysisResult && !building;
  const matchingPropertyInfo = {
    address: displayAddress,
    floor:
      vacancyInput?.floorUnit.trim() ||
      (isPropertyPreview ? mockReportData.floor : '층 정보 확인 필요'),
    area:
      areaValue !== null && areaValue !== undefined
        ? formatArea(areaValue)
        : isPropertyPreview
          ? mockReportData.area
          : '면적 확인 필요',
  };
  const facilityValue = building?.facility.value;
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

  // 입점 규제(금지·조건부)가 걸린 후보 업종 — 따로 장을 두지 않고 주소 아래에 짧게 표시한다.
  const regulatedCandidates = analysisResult
    ? [...analysisResult.top5, ...analysisResult.excluded_candidates].filter(
        (item) => item.G === '금지' || item.G === '조건부'
      )
    : [];
  const regulatedCount = regulatedCandidates.length;
  const regulatedNames = regulatedCandidates
    .slice(0, 3)
    .map((item) => item.industry_name);

  const top = analysisResult?.top5[0];
  const topName = analysisResult
    ? top?.industry_name
    : mockReportData.recommended[0]?.name;
  const summaryText = analysisResult
    ? renderSegments(analysisResult.summary_segments, factIndex)
    : mockReportData.aiAnalysisSummary.recommendationReason;
  const topReason = top
    ? renderSegments(top.reasons_segments, factIndex).trim()
    : '';
  const primaryReasons = analysisResult
    ? topReason
      ? [topReason]
      : []
    : (mockReportData.recommended[0]?.tags ?? []);
  const matchingRecommendations = analysisResult
    ? analysisResult.top5.slice(0, 3).map((candidate) => ({
        name: candidate.industry_name,
      }))
    : mockReportData.recommended.slice(0, 3).map((candidate) => ({
        name: candidate.name,
      }));
  const topChecks = top ? candidateChecks(top, factIndex) : [];
  // 결과 전체에 걸린 확인 조건과 한계(평가 미완료 등)
  const resultChecks = analysisResult
    ? renderSegments(analysisResult.confirmation_conditions_segments, factIndex)
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
    : [];
  const reviewerList =
    analysisResult?.evaluator_reviews ?? mockReportData.evaluatorReviews;
  const limitations = analysisResult
    ? renderSegments(analysisResult.limitations_segments, factIndex).trim()
    : '';
  const navigation = (
    <nav aria-label="리포트 목차" className="flex flex-col gap-1">
      {chapters.map(([id, label], index) => (
        <a
          key={id}
          href={`#${id}`}
          onClick={() => setMenuOpen(false)}
          aria-current={active === id ? 'location' : undefined}
          className={`flex min-h-12 items-center gap-3 rounded-xl px-4 py-3 text-base${id === 'listing' ? ' report-screen-only' : ''}`}
          style={{
            color: active === id ? reportPalette.brand : colors.text.secondary,
            fontWeight: active === id ? 700 : 400,
          }}
        >
          <span className="toc-number">
            {String(index + 1).padStart(2, '0')}
          </span>
          <span>{label}</span>
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
        className="report-page mx-auto max-w-[1360px] px-5 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-0 sm:px-8"
        // 기본은 사이트 글씨 배율을 그대로 쓰고, "글씨 크게 보기"는 그 위에 1.2배를 곱한다.
        style={
          {
            '--font-scale': largeText
              ? 'calc(var(--site-font-scale) * 1.2)'
              : 'var(--site-font-scale)',
          } as CSSProperties
        }
      >
        <div className="report-intro">
          <div className="report-top-actions mb-6 flex flex-wrap items-center justify-between gap-4">
            <Link
              href="/reports"
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
              <span className="mr-2 text-[#1E44B8]" aria-hidden="true">
                Aa
              </span>
              {largeText ? '기본 글씨로 보기' : '글씨 크게 보기'}
            </button>
          </div>
          <header className="report-masthead">
            <div>
              <p className="report-masthead-eyebrow">ANALYSIS REPORT</p>
              <h1 className="report-cover-title">상가 업종 분석 리포트</h1>
              <ul className="report-masthead-meta">
                <li>
                  <MapPin size={16} aria-hidden="true" />
                  {displayAddress}
                </li>
                <li>분석일 {analyzedDate}</li>
                <li>반경 {radiusLabel}</li>
              </ul>
            </div>
          </header>
        </div>
        <div
          className="report-mobile-toc sticky z-20 mb-4 border-y bg-white lg:hidden"
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
              className="report-mobile-toc-menu overflow-auto p-2"
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
            <div className="report-toc-head flex items-center justify-between">
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
              <div className="space-info">
                <header className="property-card-address space-address-heading">
                  <p className="property-address-label">분석 대상 주소</p>
                  <h3 className="property-address">{displayAddress}</h3>
                  {regulatedNames.length > 0 && (
                    <p className="property-regulation-note">
                      <TriangleAlert size={16} aria-hidden="true" />
                      <span>
                        입점 규제 확인 필요 · {regulatedNames.join(', ')}
                        {regulatedCount > regulatedNames.length &&
                          ` 외 ${regulatedCount - regulatedNames.length}개`}{' '}
                        업종은 이 자리에서 금지·조건부 대상이에요.
                      </span>
                    </p>
                  )}
                </header>
                <div className="property-photo-layout space-report-layout">
                  <PropertyMap address={displayAddress} />
                  <div className="property-preview-info space-report-info">
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
                            (areaValue !== null &&
                              areaValue !== undefined)) && (
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
                            (isPropertyPreview
                              ? mockReportData.floor
                              : '미입력')}
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
              </div>
            </Chapter>
            <Chapter id="conclusion" title="이 상가의 핵심 결론">
              <div className="dcs">
                <div className="dcs-main">
                  <section className="dcs-feature" aria-label="추천 업종 요약">
                    <div className="dcs-feature-top">
                      <span className="dcs-feature-icon" aria-hidden="true">
                        <Building2 size={23} strokeWidth={1.8} />
                      </span>
                      <p className="dcs-label">가장 먼저 검토할 업종</p>
                    </div>
                    <h3 className="dcs-feature-name">
                      {topName ?? '추천 결과 없음'}
                    </h3>
                    <p className="dcs-feature-sub">
                      공간 조건과 주변 상권 분석 결과
                    </p>
                    <div className="dcs-direction">
                      <p className="dcs-direction-label">검토 방향</p>
                      <p className="dcs-direction-text">
                        {highlightName(
                          analysisResult
                            ? summaryText
                            : `${topName}를 우선 검토하되, 4층 접근성과 급·배수 조건을 확인하세요.`,
                          topName
                        )}
                      </p>
                    </div>
                  </section>

                  <div className="dcs-evidence">
                    <div className="dcs-block-head">
                      <div>
                        <p className="dcs-eyebrow">WHY THIS INDUSTRY</p>
                        <h3>추천 근거</h3>
                      </div>
                      {primaryReasons.length > 0 && (
                        <p>주요 판단 기준 {primaryReasons.length}개</p>
                      )}
                    </div>
                    {primaryReasons.length === 0 ? (
                      <p className="dcs-empty">제공된 추천 근거가 없습니다.</p>
                    ) : (
                      <ol className="dcs-reasons">
                        {primaryReasons.map((reason, i) => {
                          const target = /폐업|개업|증가|감소|추이/.test(reason)
                            ? '#lifecycle'
                            : /인구|연령|통행/.test(reason)
                              ? '#customers'
                              : '#competition';
                          return (
                            <li key={i}>
                              <span className="dcs-num">
                                {String(i + 1).padStart(2, '0')}
                              </span>
                              <div>
                                <p className="dcs-reason-title">{reason}</p>
                                <p className="dcs-reason-desc">
                                  {reasonDescription(reason, target)}
                                </p>
                              </div>
                              <a
                                className="dcs-link"
                                href={target}
                                aria-label={`${reason} 분석 근거 보기`}
                              >
                                근거 보기 <ChevronRight size={16} />
                              </a>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                  </div>
                </div>

                <div className="dcs-block dcs-checks">
                  <div className="dcs-block-head">
                    <h3>
                      <TriangleAlert size={22} aria-hidden="true" />
                      입점 전 직접 확인
                    </h3>
                  </div>
                  {analysisResult ? (
                    topChecks.length || resultChecks.length ? (
                      <div className="dcs-check-grid">
                        {[...topChecks, ...resultChecks].map((text, i) => (
                          <div key={i}>
                            <p className="dcs-check-eyebrow">
                              {String(i + 1).padStart(2, '0')}
                            </p>
                            <p className="dcs-check-desc">{text}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="dcs-empty">
                        분석 결과에 별도 조건이 기재되지 않았습니다. 현장에서
                        입점 조건을 확인하세요.
                      </p>
                    )
                  ) : (
                    <div className="dcs-check-grid">
                      <div>
                        <p className="dcs-check-eyebrow">01 · 접근성</p>
                        <h4>접근성과 노출</h4>
                        <p className="dcs-check-desc">
                          4층까지의 엘리베이터 동선과 간판 노출을 확인하세요.
                        </p>
                      </div>
                      <div>
                        <p className="dcs-check-eyebrow">02 · 설비</p>
                        <h4>설비와 공사 조건</h4>
                        <p className="dcs-check-desc">
                          급·배수, 전력 용량과 공사 허용 범위를 확인하세요.
                        </p>
                      </div>
                      <div>
                        <p className="dcs-check-eyebrow">03 · 규제</p>
                        <h4>입점 규제</h4>
                        <p className="dcs-check-desc">
                          학교 주변 보호구역과 대상 업종의 제한 여부를
                          확인하세요.
                        </p>
                        <a className="dcs-link" href="#space">
                          규제 표시 보기 <ChevronRight size={16} />
                        </a>
                      </div>
                    </div>
                  )}
                </div>

                <a className="dcs-compare" href="#compare">
                  업종 순위 비교하기 <ArrowDownRight size={20} />
                </a>
              </div>
            </Chapter>
            <Chapter id="compare" title="이 상가에 맞는 업종 순위">
              <IndustryReview
                top5={analysisResult?.top5}
                excluded={analysisResult?.excluded_candidates}
                conditionExcluded={analysisResult?.condition_excluded}
                facts={factIndex}
              />
            </Chapter>
            <Chapter
              id="reviews"
              title="같은 추천 결과를, 서로 다른 입장에서 살펴봤어요."
              aside={`${
                reviewerList.filter((r) => r.status === 'completed').length
              } / ${reviewerList.length}명 검토 완료`}
            >
              <EvaluatorReviews
                reviews={reviewerList}
                resolutions={
                  analysisResult?.review_resolutions ??
                  mockReportData.reviewResolutions
                }
                facts={
                  analysisResult
                    ? factIndex
                    : indexFacts(mockReportData.reviewFacts)
                }
                limitations={limitations}
              />
            </Chapter>
            <Chapter
              id="customers"

              title="주변에는 어떤 사람들이 오갈까요?"
            >
              {analysisResult ? (
                floatingPopulationData ? (
                  <FactFloatingPopulationSection
                    data={floatingPopulationData}
                  />
                ) : (
                  <MissingData
                    label="유동인구"
                    state={factsState}
                    onRetry={retryFacts}
                  />
                )
              ) : (
                <FloatingPopulationSection reportLayout compactReference />
              )}
            </Chapter>
            <Chapter
              id="competition"

              title="같은 업종은 얼마나 있을까요?"
            >
              {analysisResult ? (
                competitorData ? (
                  <FactCompetitionSection data={competitorData} />
                ) : (
                  <MissingData
                    label="경쟁업체"
                    state={factsState}
                    onRetry={retryFacts}
                  />
                )
              ) : (
                <CompetitorAnalysisSection reportLayout />
              )}
            </Chapter>
            <Chapter
              id="lifecycle"

              title="새로 열고, 문을 닫는 흐름은?"
            >
              {analysisResult ? (
                businessLifecycleData ? (
                  <FactLifecycleSection data={businessLifecycleData} />
                ) : (
                  <MissingData
                    label="개폐업"
                    state={factsState}
                    onRetry={retryFacts}
                  />
                )
              ) : (
                <OpenCloseTrendSection reportLayout compactReference />
              )}
            </Chapter>
            <Chapter id="listing" title="임차인 찾기" screenOnly>
              <TenantMatchingProposal
                recommendations={matchingRecommendations}
                propertyInfo={matchingPropertyInfo}
              />
            </Chapter>
          </main>
        </div>
      </div>
    </div>
  );
}
