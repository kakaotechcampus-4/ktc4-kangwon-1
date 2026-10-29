'use client';

import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import { Menu, MapPin, TriangleAlert } from 'lucide-react';
import Header from '@/components/layout/Header';
import PropertyMap from '@/components/report/PropertyMap';
import { candidateChecks } from '@/lib/api/candidates';
import IndustryRankingList from '@/components/report/IndustryRankingList';
import { INDUSTRIES } from '@/lib/api/industries';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import {
  FactCompetitionSection,
  FactFloatingPopulationSection,
  FactLifecycleSection,
} from '@/components/report/FactSections';
import EvaluatorReviews from '@/components/report/EvaluatorReviews';
import KeyConclusion from '@/components/report/KeyConclusion';
import TenantMatchingProposal from '@/components/report/TenantMatchingProposal';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import './report.css';
import { mockReportData } from '@/lib/mockData/report';
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
  // 화면에서만 보이고 인쇄에서는 빠지는 장(임차인 찾기)
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
  const [demoReport, setDemoReport] = useState<ReportSummary | null>(null);
  const [isDemoReport, setIsDemoReport] = useState(false);
  // 분석 결과와 함께 입력한 주소 정보를 불러온다.
  const [vacancyInput, setVacancyInput] = useState<VacancyInput | null>(null);
  const [building, setBuilding] = useState<BuildingInfo | null>(null);

  useEffect(() => {
    // sessionStorage는 브라우저 전용이라 서버 렌더에서는 접근할 수 없다.
    // 예시 리포트는 카드에서 전달한 고정 목업 데이터만 사용해, 이전 입력 주소와
    // 섞이지 않도록 한다. 실제 리포트에서만 sessionStorage의 최신 결과를 읽는다.
    const demoId = new URLSearchParams(window.location.search).get('demo');
    if (demoId !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsDemoReport(true);
      setDemoReport(mockReports.find((report) => report.id === demoId) ?? null);
      return;
    }
    const savedResult = loadAnalysisResult();
    if (!savedResult) {
      // 결과가 없는 직접 진입은 예시 리포트로 보여준다. 이전에 입력한 주소만
      // 가져와 목업 분석 내용과 섞이지 않게 한다.
      setIsDemoReport(true);
      return;
    }
    setAnalysisResult(savedResult);
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

  const analyzedDate =
    demoReport?.analyzedDate ??
    (analysisResult
      ? new Date().toLocaleDateString('ko-KR')
      : mockReportData.analyzedDate);
  const inputAddress = vacancyInput
    ? [vacancyInput.roadAddress, vacancyInput.floorUnit.trim()]
        .filter(Boolean)
        .join(' ')
    : undefined;
  const address = isDemoReport
    ? (demoReport?.address ?? mockReportData.address)
    : (inputAddress ?? mockReportData.address);
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
                  <PropertyMap address={displayAddress} />
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
              <KeyConclusion
                name={topName}
                industryCode={top?.industry_code}
                badge={top?.badge}
                checks={
                  analysisResult
                    ? [...topChecks, ...resultChecks]
                    : [
                        '4층까지의 엘리베이터 동선과 간판 노출을 확인하세요.',
                        '급·배수, 전력 용량과 공사 허용 범위를 확인하세요.',
                        '학교 주변 보호구역과 대상 업종의 제한 여부를 확인하세요.',
                      ]
                }
                facts={factIndex}
              />
            </Chapter>
            <Chapter
              id="compare"
              title="분석한 51개 업종을 검토 순서대로 정리했어요. 순위는 업종 간 비교를 돕는 참고 자료이며, 실제 입점 가능 여부와는 별도로 확인해야 합니다."
              aside={`${Object.keys(INDUSTRIES).length}개 업종`}
            >
              <IndustryRankingList />
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
                  <FactCompetitionSection
                    data={competitorData}
                    recommendedCodes={
                      new Set(
                        analysisResult.top5.map((item) => item.industry_code)
                      )
                    }
                  />
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
