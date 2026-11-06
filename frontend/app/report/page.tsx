'use client';

import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import { Menu, MapPin, TriangleAlert, Download } from 'lucide-react';
import Header from '@/components/layout/Header';
import RequireAuth from '@/components/auth/RequireAuth';
import PropertyMap from '@/components/report/PropertyMap';
import { candidateChecks } from '@/lib/api/candidates';
import IndustryRankingList from '@/components/report/IndustryRankingList';
import {
  mockRankingView,
  rankingView,
} from '@/components/report/industryRanking';
import { INDUSTRIES } from '@/lib/api/industries';
import {
  FactCompetitionSection,
  FactFloatingPopulationSection,
  FactLifecycleSection,
} from '@/components/report/FactSections';
import EvaluatorReviews from '@/components/report/EvaluatorReviews';
import KeyConclusion, {
  getKeyConclusionItems,
} from '@/components/report/KeyConclusion';
import TenantMatchingProposal from '@/components/report/TenantMatchingProposal';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import './report.css';
import { mockReportData } from '@/lib/mockData/report';
import {
  mockCompetitionFacts,
  mockFloatingPopulationFacts,
  mockLifecycleFacts,
  mockRecommendedIndustryCodes,
} from '@/lib/mockData/reportPresentation';
import { mockReports, type ReportSummary } from '@/lib/mockData/reports';
import { mockProperty } from '@/lib/mockData/property';
import {
  loadAnalysisResult,
  loadAnalysisFacts,
  loadRequestId,
  saveAnalysisFacts,
  loadConfirmedBuilding,
  ANALYSIS_RADIUS_M,
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
import { getAnalysis, getAnalysisFacts } from '@/lib/api/analyses';
import { indexFacts, renderSegments } from '@/lib/api/segments';
import {
  EDUCATION_ZONE_LABELS,
  educationZoneStatus,
} from '@/lib/api/educationZone';
import { MOCK_MODE } from '@/lib/api/mockMode';
import {
  isExampleReport,
  reportSource,
  storedReport,
  type Coordinates,
} from '@/lib/api/reportSource';
import { formatDay } from '@/lib/api/analysisStatus';
import { reportPdfTitle } from '@/lib/api/reportPdf';
import { printReport } from '@/lib/api/reportPrint';
import StateNotice from '@/components/ui/StateNotice';
import {
  fetchFailed,
  reportNotice,
  type ReportNoticeState,
} from '@/components/report/reportNotice';
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
  // 화면에서만 보이고 인쇄에서는 제외하는 다음 단계
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
          {id === 'reviews' && aside && (
            <span className="chapter-aside-inline-mobile">{aside}</span>
          )}
        </h2>
        {/* 핵심 결론은 패널 자체가 설명이라 소개 문장을 두지 않는다 */}
        {id !== 'conclusion' && (
          <div className="chapter-description-row">
            <p className="chapter-description">
              {id === 'space'
                ? '분석 대상 상가의 기본 정보를 확인하세요.'
                : id === 'listing'
                  ? '추천 업종을 바탕으로 실제 임차인을 찾아보세요.'
                  : title}
            </p>
            {aside && <span className="chapter-aside">{aside}</span>}
          </div>
        )}
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
export default function ReportPage() {
  const [example, setExample] = useState<boolean>();
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExample(isExampleReport(window.location.search));
  }, []);
  if (example === undefined) {
    return null;
  }
  return example ? (
    <ReportContent />
  ) : (
    <RequireAuth>
      <ReportContent />
    </RequireAuth>
  );
}

function ReportContent() {
  const [active, setActive] = useState<string>('space');
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    if (!menuOpen || !window.matchMedia('(max-width: 480px)').matches) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [menuOpen]);
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
  const [demoReport, setDemoReport] = useState<ReportSummary | null>(null);
  const [isDemoReport, setIsDemoReport] = useState(false);
  // 분석 결과와 함께 입력한 주소 정보를 불러온다.
  const [vacancyInput, setVacancyInput] = useState<VacancyInput | null>(null);
  const [building, setBuilding] = useState<BuildingInfo | null>(null);
  // 분석이 쓴 좌표. 지도 중심이자 반경 원의 중심이다. 없으면 지도가 주소로 찾는다.
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);

  const [notice, setNotice] = useState<ReportNoticeState | null | undefined>();
  const [analyzedDay, setAnalyzedDay] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    // sessionStorage는 브라우저 전용이라 서버 렌더에서는 접근할 수 없다.
    // 예시 리포트는 카드에서 전달한 고정 목업 데이터만 사용해, 이전 입력 주소와
    // 섞이지 않도록 한다. 실제 리포트에서만 sessionStorage의 최신 결과를 읽는다.
    const params = new URLSearchParams(window.location.search);
    const source = reportSource({
      urlId: params.get('id'),
      savedRequestId: loadRequestId(),
      saved: loadAnalysisResult(),
      mockMode: MOCK_MODE,
      example: isExampleReport(window.location.search),
    });
    if (source.kind !== 'fetch') {
      const demoId = params.get('demo');
      const isDemo = source.kind === 'example' || source.kind === 'preview';
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsDemoReport(isDemo);
      setDemoReport(
        isDemo && demoId !== null
          ? (mockReports.find((report) => report.id === demoId) ?? null)
          : null
      );
      setAnalysisResult(source.kind === 'saved' ? source.result : null);
      setVacancyInput(source.kind === 'saved' ? loadVacancyInput() : null);
      setBuilding(source.kind === 'saved' ? loadConfirmedBuilding() : null);
      // 미리보기·예시는 목업 상가를 가리킨다. 주소에 건물 이름이 붙어 있어
      // 좌표 없이 주소로만 찾으면 못 찾는다.
      // 저장된 결과(saved)에는 좌표가 없어 주소로 찾는다.
      setCoordinates(
        isDemo
          ? {
              latitude: mockProperty.latitude,
              longitude: mockProperty.longitude,
            }
          : null
      );
      setNotice(source.kind === 'empty' ? { kind: 'empty' } : null);
      return;
    }
    let cancelled = false;
    setNotice({ kind: 'loading' });
    getAnalysis(source.requestId)
      .then((detail) => {
        if (cancelled) return;
        const report = storedReport(detail);
        if (report.kind !== 'ready') {
          setNotice(report);
          return;
        }
        setAnalysisResult(report.result);
        setVacancyInput(report.vacancyInput);
        setBuilding(null);
        setCoordinates(report.coordinates);
        setAnalyzedDay(report.analyzedDate);
        setNotice(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setNotice(
          fetchFailed(error, () => setLoadAttempt((attempt) => attempt + 1))
        );
      });
    return () => {
      cancelled = true;
    };
  }, [loadAttempt]);

  // 차트용 전체 fact. 결과의 facts는 보고서가 인용한 것만 담아 따로 받는다.
  // undefined = 받는 중, null = 받지 못함
  const [allFacts, setAllFacts] = useState<FactView[] | null | undefined>();
  // "다시 불러오기"를 누를 때마다 바뀌어 조회를 다시 시작한다.
  const [factsAttempt, setFactsAttempt] = useState(0);
  useEffect(() => {
    if (!analysisResult) {
      return;
    }
    const requestId = analysisResult.request_id;
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
  const facts = [...(allFacts ?? []), ...(analysisResult?.facts ?? [])];
  const factIndex = indexFacts(facts);
  // 보호구역 판정. 걸린 상가만 지도에 주변 학교를 함께 표시한다.
  const educationZone = educationZoneStatus(facts);
  const candidateCodes = analysisResult
    ? [
        ...analysisResult.top5.map((item) => item.industry_code),
        ...analysisResult.excluded_candidates.map((item) => item.industry_code),
      ]
    : [];
  const floatingPopulationData = allFacts
    ? floatingPopulationFromFacts(allFacts)
    : isDemoReport
      ? mockFloatingPopulationFacts
      : null;
  const competitorData = allFacts
    ? competitionFromFacts(allFacts, candidateCodes)
    : isDemoReport
      ? mockCompetitionFacts
      : null;
  const businessLifecycleData = allFacts
    ? lifecycleFromFacts(allFacts, candidateCodes)
    : isDemoReport
      ? mockLifecycleFacts
      : null;

  const analyzedDate =
    demoReport?.analyzedDate ??
    (analysisResult
      ? analyzedDay || formatDay(new Date().toISOString())
      : mockReportData.analyzedDate);
  const inputAddress = vacancyInput
    ? [vacancyInput.roadAddress, vacancyInput.floorUnit.trim()]
        .filter(Boolean)
        .join(' ')
    : undefined;
  const address = isDemoReport
    ? (demoReport?.address ?? mockReportData.address)
    : (inputAddress ?? mockReportData.address);
  const pdfTitle = reportPdfTitle({
    example: isDemoReport,
    address,
    analyzedDate,
  });
  const displayAddress = address.replace(/\s+\d+층(?:\s+\d+호)?$/, '');
  const parkingValue = building?.parking.value;
  const areaValue = building?.exclusiveAreaM2.value;
  const isPropertyPreview = !vacancyInput && !analysisResult && !building;
  const facilityValue = building?.facility.value;
  const facilityLabel = facilityValue
    ? FACILITY_LABELS[facilityValue]
    : isPropertyPreview
      ? mockProperty.facility
      : '조회 필요';
  const sewageLabel =
    building?.sewage.value ??
    (isPropertyPreview ? mockProperty.sewage : '조회 필요');
  const radiusLabel = `${ANALYSIS_RADIUS_M}m`;
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
  const topChecks = top ? candidateChecks(top, factIndex) : [];
  // 결과 전체에 걸린 확인 조건과 한계(평가 미완료 등)
  const resultChecks = analysisResult
    ? renderSegments(analysisResult.confirmation_conditions_segments, factIndex)
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
    : [];
  const conclusionChecks = analysisResult
    ? [...topChecks, ...resultChecks]
    : [
        '1층에서 출입구와 간판이 잘 보이는지 현장에서 확인하세요.',
        '업종에 필요한 급·배수, 전력 용량과 공사 허용 범위를 확인하세요.',
        '건축물 용도와 해당 공간에서 영업 가능한 업종을 확인하세요.',
      ];
  const conclusionCheckCount = getKeyConclusionItems(conclusionChecks).length;
  const summaryText = analysisResult
    ? renderSegments(analysisResult.summary_segments, factIndex).trim()
    : '';
  const ranking = analysisResult
    ? rankingView(analysisResult, factIndex)
    : mockRankingView();
  const rankingCount = analysisResult
    ? analysisResult.ranking?.length
      ? Object.keys(INDUSTRIES).length
      : analysisResult.top5.length
    : Object.keys(INDUSTRIES).length;
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
          className="flex min-h-12 items-center gap-3 rounded-xl px-4 py-3 text-base"
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
  const shownNotice: ReportNoticeState | null =
    notice === undefined ? { kind: 'loading' } : notice;
  if (shownNotice) {
    return (
      <div
        className="flex min-h-screen flex-col"
        style={{ backgroundColor: colors.neutral.background }}
      >
        <Header />
        <main className="mx-auto flex w-full max-w-[880px] flex-col gap-8 px-4 pt-14 pb-24 sm:px-8">
          <StateNotice {...reportNotice(shownNotice)} />
        </main>
      </div>
    );
  }
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
              href={isDemoReport || MOCK_MODE ? '/reports' : '/my/reports'}
              className="inline-flex min-h-11 items-center text-sm"
            >
              ← 리포트 목록 보기
            </Link>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => printReport(pdfTitle)}
                className="inline-flex h-11 shrink-0 items-center rounded-md border bg-white px-4 text-sm font-semibold"
                style={{ borderColor: colors.neutral.border }}
              >
                <Download
                  size={16}
                  className="mr-2 text-[#1E44B8]"
                  aria-hidden="true"
                />
                PDF 다운로드
              </button>
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
          </div>
          <header className="report-masthead">
            <div>
              <p className="report-masthead-eyebrow">ANALYSIS REPORT</p>
              <h1 className="report-cover-title">상가 업종 분석 리포트</h1>
              <ul className="report-masthead-meta">
                {isDemoReport && <li>예시 리포트 · 목업 데이터</li>}
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
            <span className="report-mobile-toc-current">
              <span className="report-mobile-toc-current-number">
                {String(
                  chapters.findIndex((item) => item[0] === active) + 1
                ).padStart(2, '0')}
              </span>
              <span>{chapters.find((item) => item[0] === active)?.[1]}</span>
            </span>
            <span className="flex items-center gap-2">
              <Menu size={18} />
              목차 보기
            </span>
          </button>
          {menuOpen && (
            <>
              <button
                type="button"
                aria-label="목차 닫기"
                className="report-mobile-toc-backdrop"
                onClick={() => setMenuOpen(false)}
              />
              <div
                id="mobile-report-menu"
                className="report-mobile-toc-menu overflow-auto p-2"
              >
                <p className="report-mobile-toc-sheet-title">리포트 목차</p>
                {navigation}
              </div>
            </>
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
            <Chapter id="space" title="상가 정보">
              <div className="space-info">
                <header className="property-card-address space-address-heading">
                  <p className="property-address-label">분석 대상 주소</p>
                  <h2 className="property-address">{displayAddress}</h2>
                  {analysisResult && regulatedNames.length > 0 && (
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
                  <PropertyMap
                    address={displayAddress}
                    latitude={coordinates?.latitude}
                    longitude={coordinates?.longitude}
                    radiusM={ANALYSIS_RADIUS_M}
                    showSchools={educationZone === 'inside'}
                  />
                  <div className="property-preview-info space-report-info">
                    <dl className="property-facts property-main-facts">
                      <div>
                        <dt>전용면적</dt>
                        <dd>
                          {demoReport
                            ? `${demoReport.areaPyeong}평`
                            : areaValue !== null && areaValue !== undefined
                              ? formatArea(areaValue)
                              : isPropertyPreview
                                ? mockReportData.area.replace(/^전용\s*/, '')
                                : '조회 필요'}
                          {!demoReport &&
                            (isPropertyPreview ||
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
                          {demoReport?.floor ||
                            vacancyInput?.floorUnit.trim() ||
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
                      <div>
                        {/* 분석 반경은 머리말 칩과 지도 원에 이미 있어 이 자리는
                            지도에 학교가 왜 떠 있는지를 설명하는 데 쓴다. */}
                        <dt>교육환경보호구역</dt>
                        <dd>
                          <span
                            className={
                              educationZone === 'inside'
                                ? 'property-fact-alert'
                                : undefined
                            }
                          >
                            {EDUCATION_ZONE_LABELS[educationZone]}
                          </span>
                        </dd>
                      </div>
                    </dl>
                  </div>
                </div>
              </div>
            </Chapter>
            <Chapter id="conclusion" title="이 상가의 핵심 결론">
              <KeyConclusion
                name={topName}
                industryCode={top?.industry_code}
                badge={top?.badge}
                summary={summaryText}
                checks={conclusionChecks}
                facts={factIndex}
              />
            </Chapter>
            <Chapter
              id="compare"
              title="분석한 51개 업종을 검토 순서대로 정리했어요. 순위는 업종 간 비교를 돕는 참고 자료이며, 실제 입점 가능 여부와는 별도로 확인해야 합니다."
              aside={`${rankingCount}개 업종`}
            >
              <IndustryRankingList view={ranking} totalCount={rankingCount} />
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
                checkCount={conclusionCheckCount}
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
              {floatingPopulationData ? (
                <FactFloatingPopulationSection data={floatingPopulationData} />
              ) : (
                <MissingData
                  label="유동인구"
                  state={factsState}
                  onRetry={retryFacts}
                />
              )}
            </Chapter>
            <Chapter
              id="competition"

              title="같은 업종은 얼마나 있을까요?"
            >
              {competitorData ? (
                <FactCompetitionSection
                  data={competitorData}
                  recommendedCodes={
                    analysisResult
                      ? new Set(
                          analysisResult.top5.map((item) => item.industry_code)
                        )
                      : mockRecommendedIndustryCodes
                  }
                />
              ) : (
                <MissingData
                  label="경쟁업체"
                  state={factsState}
                  onRetry={retryFacts}
                />
              )}
            </Chapter>
            <Chapter
              id="lifecycle"

              title="새로 열고, 문을 닫는 흐름은?"
            >
              {businessLifecycleData ? (
                <FactLifecycleSection data={businessLifecycleData} />
              ) : (
                <MissingData
                  label="개폐업"
                  state={factsState}
                  onRetry={retryFacts}
                />
              )}
            </Chapter>
            <Chapter id="listing" title="임차인 찾기" screenOnly>
              <TenantMatchingProposal
                recommendations={
                  analysisResult
                    ? analysisResult.top5.slice(0, 3).map((item) => ({
                        name: item.industry_name,
                      }))
                    : mockReportData.recommended.slice(0, 3).map((item) => ({
                        name: item.name,
                      }))
                }
                propertyInfo={{
                  address: displayAddress,
                  floor:
                    demoReport?.floor ||
                    vacancyInput?.floorUnit.trim() ||
                    (isPropertyPreview
                      ? mockReportData.floor
                      : '층 정보 확인 필요'),
                  area:
                    areaValue !== null && areaValue !== undefined
                      ? formatArea(areaValue)
                      : isPropertyPreview
                        ? mockReportData.area
                        : '면적 확인 필요',
                }}
              />
            </Chapter>
          </main>
        </div>
      </div>
    </div>
  );
}
