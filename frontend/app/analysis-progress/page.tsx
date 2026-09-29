'use client';

import { useRouter } from 'next/navigation';
import {
  CheckCircle2,
  Loader2,
  PauseCircle,
  type LucideIcon,
} from 'lucide-react';
import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import ProgressTracker from '@/components/analysis-progress/ProgressTracker';
import ClarifyingPanel from '@/components/analysis-progress/ClarifyingPanel';
import AnalysisSummaryPanel from '@/components/analysis-progress/AnalysisSummaryPanel';
import { colors } from '@/styles/tokens';
import {
  mockAnalysisProgress,
  type AnalysisStage,
} from '@/lib/mockData/analysisProgress';
import { useAnalysisProgressSimulation } from '@/lib/hooks/useAnalysisProgressSimulation';

// 화면 상단 문구는 stage 하나로만 정한다 — "분석 중"과 "확인 필요"가 동시에
// 보이지 않게 하려는 것. 우측 상태 표시(statusLabel/statusHint)는 짧은 시스템
// 상태만 담고, 자세한 설명은 제목·본문에서만 한다.
const STAGE_COPY: Record<
  AnalysisStage,
  {
    title: string;
    description: string;
    statusLabel: string;
    statusHint: string;
    tone: 'progress' | 'waiting' | 'done';
    Icon: LucideIcon;
  }
> = {
  analyzing: {
    title: 'AI가 공실을 분석하고 있어요',
    description:
      '입력하신 정보를 바탕으로 주변 상권, 유동인구, 개폐업 데이터를 분석하고 있습니다.',
    statusLabel: '분석 중',
    statusHint: '약 2~3분 소요',
    tone: 'progress',
    Icon: Loader2,
  },
  awaiting_input: {
    title: '분석을 계속하려면 확인이 필요해요',
    description:
      '주변 데이터 분석은 끝났어요. 업종을 최종 판단하기 전에 공간 조건 몇 가지만 알려주세요.',
    statusLabel: '답변 대기',
    statusHint: '분석이 잠시 멈췄어요',
    tone: 'waiting',
    Icon: PauseCircle,
  },
  // 중앙 영역이 "답변을 반영해 분석을 이어가고 있어요"를 크게 보여주므로
  // 제목은 겹치지 않게 전체 상황만 말한다.
  resuming: {
    title: 'AI가 분석을 마무리하고 있어요',
    description: '알려주신 조건까지 반영해 최종 판단을 내리고 있습니다.',
    statusLabel: '분석 재개',
    statusHint: '최종 결과를 준비 중이에요',
    tone: 'progress',
    Icon: Loader2,
  },
  completed: {
    title: '분석이 완료됐어요',
    description: '맞춤 리포트가 준비됐습니다.',
    statusLabel: '분석 완료',
    statusHint: '리포트를 확인해 보세요',
    tone: 'done',
    Icon: CheckCircle2,
  },
};

const TONE_COLORS = {
  progress: colors.brand.primary,
  waiting: colors.accent.orange,
  done: colors.brand.primary,
} as const;

const REPORT_PATH = '/report';

export default function AnalysisProgressPage() {
  const router = useRouter();
  // TODO: mock 타이머 대신 실제 분석 완료 신호(폴링/웹소켓)로 stage를 바꾸고,
  // 완료 시 결과를 saveAnalysisResult()로 저장해 둔다. 저장된 결과가
  // 없으면 /report는 mock 리포트를 보여준다.
  const { steps, stage, resume } = useAnalysisProgressSimulation(
    mockAnalysisProgress.steps
  );

  // 완료돼도 자동으로 넘기지 않고, 사용자가 "리포트 보기"를 눌렀을 때만
  // 이동한다. replace로 이동해 리포트에서 뒤로 가기를 눌러도 이미 끝난 진행
  // 화면(=mock이 처음부터 다시 도는 화면)으로 돌아오지 않게 한다.
  function goToReport() {
    router.replace(REPORT_PATH);
  }

  function handleAnswersSubmit(answers: Record<string, string>, note: string) {
    // mock 단계 — 실제 제출 API 없음. ClarifyingPanel이 이미 콘솔에 기록한다.
    void answers;
    void note;
    resume();
  }

  const copy = STAGE_COPY[stage];
  const toneColor = TONE_COLORS[copy.tone];

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
              className="text-[32px] leading-tight font-bold"
              style={{ color: colors.text.primary }}
            >
              {copy.title}
            </h1>
            <p
              className="text-base leading-relaxed"
              style={{ color: colors.text.secondary }}
            >
              {copy.description}
            </p>
          </div>

          <div
            className="flex shrink-0 items-center gap-3 rounded-xl px-5 py-3.5"
            style={{ backgroundColor: `${toneColor}14` }}
            role="status"
          >
            <copy.Icon
              size={20}
              className={`shrink-0 ${copy.Icon === Loader2 ? 'animate-spin' : ''}`}
              style={{ color: toneColor }}
            />
            <div className="flex flex-col gap-0.5">
              <p
                className="text-[15px] font-semibold"
                style={{
                  color:
                    copy.tone === 'waiting'
                      ? colors.accent.orange
                      : colors.brand.dark,
                }}
              >
                {copy.statusLabel}
              </p>
              <p
                className="text-[13px]"
                style={{ color: colors.text.secondary }}
              >
                {copy.statusHint}
              </p>
            </div>
          </div>
        </div>

        {/* 데스크톱 3컬럼 기준(반응형은 이번 범위 밖). 중앙 재질문 영역이 가장
            넓고, 좌측 진행 현황·우측 분석 대상은 고정 폭 보조 영역이다. */}
        <div className="grid w-full grid-cols-[340px_minmax(0,1fr)_300px] items-start gap-6">
          <ProgressTracker
            steps={steps}
            questionCount={mockAnalysisProgress.questions.length}
          />
          <ClarifyingPanel
            stage={stage}
            steps={steps}
            questions={mockAnalysisProgress.questions}
            onSubmit={handleAnswersSubmit}
            onViewReport={goToReport}
          />
          <AnalysisSummaryPanel summary={mockAnalysisProgress.summary} />
        </div>
      </main>
    </div>
  );
}
