'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus } from 'lucide-react';
import Header from '@/components/layout/Header';
import { MapIllustration } from '@/components/report/PropertyMap';
import { candidateScore } from '@/components/report/IndustryReview';
import { loadAnalysisResult, loadVacancyInput } from '@/lib/api/resultStore';
import { mockReports, type ReportSummary } from '@/lib/mockData/reports';
import { colors } from '@/styles/tokens';

/**
 * 리포트 목록. 목록 API가 없어 목업 리포트를 보여주고, 이 브라우저에서 방금
 * 분석한 결과가 있으면 맨 앞에 붙인다. 카드를 누르면 /report로 간다.
 */
export default function ReportsPage() {
  const [current, setCurrent] = useState<ReportSummary | null>(null);

  useEffect(() => {
    // sessionStorage는 브라우저 전용이라 마운트 후에 읽는다.
    const result = loadAnalysisResult();
    const input = loadVacancyInput();
    const top = result?.top5[0];
    if (!result || !top) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrent({
      id: result.request_id,
      address: input?.roadAddress || '방금 분석한 상가',
      floor: input?.floorUnit.trim() || '층 미입력',
      areaPyeong: 0,
      analyzedDate: new Date().toLocaleDateString('ko-KR'),
      topIndustry: top.industry_name,
      score: candidateScore(top)?.low ?? 0,
    });
  }, []);

  const reports = current ? [current, ...mockReports] : mockReports;

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="mx-auto w-full max-w-[1280px] px-4 pt-14 pb-24 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p
              className="text-sm font-bold tracking-[0.08em]"
              style={{ color: colors.brand.primary }}
            >
              ANALYSIS REPORTS
            </p>
            <h1
              className="mt-3 font-extrabold tracking-[-0.04em]"
              style={{
                color: colors.brand.dark,
                fontSize: 'clamp(30px, 3vw, 42px)',
              }}
            >
              리포트 목록
            </h1>
          </div>
          <Link
            href="/vacancy-input"
            className="inline-flex h-12 items-center gap-2 rounded-xl px-5 text-base font-bold text-white transition-opacity hover:opacity-90"
            style={{ backgroundColor: colors.brand.primary }}
          >
            <Plus size={18} aria-hidden="true" />새 공실 분석
          </Link>
        </div>

        <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {reports.map((report) => (
            <li key={report.id}>
              <ReportCard report={report} />
            </li>
          ))}
          <li>
            <Link
              href="/vacancy-input"
              className="flex h-full min-h-[420px] flex-col items-center justify-center gap-3 rounded-[22px] border-2 border-dashed border-[#C9D3DE] bg-white/60 transition-all duration-200 hover:-translate-y-1.5 hover:border-[#2453D6] hover:bg-white"
            >
              <span
                className="flex size-14 items-center justify-center rounded-2xl"
                style={{ backgroundColor: colors.brand.wash }}
              >
                <Plus
                  size={26}
                  aria-hidden="true"
                  color={colors.brand.primary}
                />
              </span>
              <span
                className="text-lg font-bold"
                style={{ color: colors.brand.dark }}
              >
                새 공실 분석
              </span>
              <span className="text-sm text-[#6B7886]">
                공실을 추가해 분석하세요
              </span>
            </Link>
          </li>
        </ul>
      </main>
    </div>
  );
}

function ReportCard({ report }: { report: ReportSummary }) {
  const meta = [
    report.floor,
    report.areaPyeong ? `${report.areaPyeong}평` : null,
    report.analyzedDate,
  ].filter(Boolean);

  return (
    <Link
      href="/report"
      aria-label={`${report.address} 리포트 보기 · AI 추천 ${report.topIndustry} ${report.score}점`}
      className="group block overflow-hidden rounded-[22px] bg-white shadow-[0_10px_30px_rgba(16,35,58,0.06)] transition-all duration-200 ease-out hover:-translate-y-1.5 hover:shadow-[0_22px_44px_rgba(16,35,58,0.14)] focus-visible:-translate-y-1.5"
    >
      <div className="relative h-48 overflow-hidden">
        <div className="absolute inset-0 transition-transform duration-300 group-hover:scale-105">
          <MapIllustration />
        </div>
        <span
          className="absolute bottom-4 left-4 rounded-lg px-3 py-1.5 text-sm font-bold text-white"
          style={{ backgroundColor: colors.brand.primary }}
        >
          분석 완료
        </span>
      </div>
      <div className="p-7">
        <p
          className="truncate text-xl font-extrabold tracking-[-0.02em]"
          style={{ color: colors.brand.dark }}
        >
          {report.address}
        </p>
        <p className="mt-1.5 text-sm text-[#6B7886]">{meta.join(' · ')}</p>
        <div className="my-5 h-px bg-[#E2E8EE]" />
        <p className="text-13 font-bold tracking-[0.08em] text-[#6B7886]">
          AI 추천
        </p>
        <p className="mt-2 flex items-baseline gap-2.5">
          <span
            className="text-2xl font-extrabold"
            style={{ color: colors.brand.dark }}
          >
            {report.topIndustry}
          </span>
          <span
            className="text-2xl font-extrabold"
            style={{ color: colors.brand.primary }}
          >
            {report.score}점
          </span>
        </p>
        <div
          className="mt-4 h-2 rounded-full bg-[#E2E8EE]"
          role="img"
          aria-label={`적합도 ${report.score}점`}
        >
          <div
            className="h-2 rounded-full"
            style={{
              width: `${Math.min(100, Math.max(0, report.score))}%`,
              backgroundColor: colors.brand.primary,
            }}
          />
        </div>
      </div>
    </Link>
  );
}
