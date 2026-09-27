'use client';

import { Sparkles } from 'lucide-react';
import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import ProgressTracker from '@/components/analysis-progress/ProgressTracker';
import ClarifyingChat from '@/components/analysis-progress/ClarifyingChat';
import AnalysisSummaryPanel from '@/components/analysis-progress/AnalysisSummaryPanel';
import { colors } from '@/styles/tokens';
import { mockAnalysisProgress } from '@/lib/mockData/analysisProgress';
import { useAnalysisProgressSimulation } from '@/lib/hooks/useAnalysisProgressSimulation';

export default function AnalysisProgressPage() {
  const { phases, elapsedSeconds } = useAnalysisProgressSimulation(
    mockAnalysisProgress.phases,
    {
      onComplete: () => {
        // 실제 백엔드 연동 전 mock 타이머로 흉내만 낸다.
        // TODO: 실제 분석 완료 신호(폴링/웹소켓)로 교체하고, 완료 시 이동할
        // 리포트 라우트를 연결한다. 지금 /report 페이지는 이 화면을 거치지
        // 않는 별도 흐름(AddressInput 제출 → 바로 이동)에 연결돼 있어서,
        // 이 화면이 그 흐름과 어떻게 합쳐질지 아직 정해지지 않았다.
        console.log('[AnalysisProgressPage] 분석 시뮬레이션 완료(mock)');
      },
    }
  );

  function handleChatSubmit(answers: Record<string, string>, freeText: string) {
    // mock 단계 — 실제 제출 API 없음. ClarifyingChat이 이미 콘솔에 기록한다.
    void answers;
    void freeText;
  }

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="flex w-full flex-col items-start gap-8 px-8 py-10">
        <StepIndicator currentStep={2} />

        <div className="flex w-full items-start justify-between gap-6">
          <div className="flex flex-col items-start gap-3">
            <h1
              className="text-[32px] font-bold"
              style={{ color: colors.neutral.black }}
            >
              AI가 공실을 분석하고 있어요
            </h1>
            <p className="text-base" style={{ color: 'var(--color-gray-500)' }}>
              입력하신 정보를 바탕으로 주변 상권, 유동인구, 개폐업 데이터 등을
              분석하고 있습니다.
            </p>
          </div>

          <div
            className="flex shrink-0 items-start gap-3 rounded-xl p-4"
            style={{ backgroundColor: `${colors.brand.primary}14` }}
          >
            <Sparkles
              size={18}
              className="mt-0.5 shrink-0"
              style={{ color: colors.brand.primary }}
            />
            <div className="flex flex-col gap-0.5">
              <p
                className="text-sm font-semibold"
                style={{ color: colors.brand.dark }}
              >
                약 2~3분 정도 소요돼요
              </p>
              <p className="text-xs" style={{ color: 'var(--color-gray-500)' }}>
                분석이 완료되면 자동으로 다음 단계로 이동합니다.
              </p>
            </div>
          </div>
        </div>

        {/* 데스크톱 3컬럼 레이아웃 기준으로만 만든다(반응형은 이번 범위 밖). */}
        <div className="grid w-full grid-cols-3 items-start gap-6">
          <ProgressTracker phases={phases} elapsedSeconds={elapsedSeconds} />
          <ClarifyingChat
            questions={mockAnalysisProgress.questions}
            onSubmit={handleChatSubmit}
          />
          <AnalysisSummaryPanel summary={mockAnalysisProgress.summary} />
        </div>
      </main>
    </div>
  );
}
