'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  PauseCircle,
  type LucideIcon,
} from 'lucide-react';
import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import FlowPageTitle from '@/components/form/FlowPageTitle';
import ProgressTracker from '@/components/analysis-progress/ProgressTracker';
import ClarifyingPanel from '@/components/analysis-progress/ClarifyingPanel';
import AnalysisSummaryPanel from '@/components/analysis-progress/AnalysisSummaryPanel';
import { colors } from '@/styles/tokens';
import { formatArea } from '@/components/building-confirm/labels';
import { normalizeFloor } from '@/lib/api/building';
import {
  mockAnalysisProgress,
  type AnalysisStage,
  type AnalysisSummary,
  type ClarifyingQuestion,
  type ClarifyingAnswers,
} from '@/lib/mockData/analysisProgress';
import { demoClarifyingQuestions } from '@/lib/mockData/clarifyingDemo';
import {
  loadConfirmedBuilding,
  loadVacancyInput,
  saveAnalysisResult,
  saveRequestId,
} from '@/lib/api/resultStore';
import { MOCK_MODE } from '@/lib/api/mockMode';
import {
  prefillAnswers,
  toAnswerSubmission,
  toClarifyingQuestions,
} from '@/lib/api/adapters/progress';
import { useAnalysisProgress } from '@/lib/hooks/useAnalysisProgress';
import { useAnalysisProgressSimulation } from '@/lib/hooks/useAnalysisProgressSimulation';
import type { ProgressStep } from '@/lib/mockData/analysisProgress';

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
    tone: 'progress' | 'waiting' | 'done' | 'error';
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
  failed: {
    title: '분석을 마치지 못했어요',
    description:
      '잠시 후 다시 시도해 주세요. 입력하신 정보는 그대로 남아 있어요.',
    statusLabel: '분석 실패',
    statusHint: '다시 시도해 주세요',
    tone: 'error',
    Icon: AlertCircle,
  },
};

const TONE_COLORS = {
  progress: colors.brand.primary,
  waiting: colors.accent.orange,
  done: colors.brand.primary,
  error: colors.status.notRecommend,
} as const;

const REPORT_PATH = '/report';
// 1평 = 약 3.3058㎡
const PYEONG_M2 = 3.3058;

// 앞 단계(주소 입력·상가 정보 확인)에서 받은 값. 분석 대상 패널과
// 질문 미리 채우기에 쓴다.
type KnownSite = {
  summary: AnalysisSummary;
  floor?: string;
  exclusiveArea?: string;
  parking?: string | null;
};

function useKnownSite(): KnownSite {
  const [known, setKnown] = useState<KnownSite>({
    summary: mockAnalysisProgress.summary,
  });

  useEffect(() => {
    const input = loadVacancyInput();
    if (!input) {
      return;
    }
    const building = loadConfirmedBuilding();
    const area = building?.exclusiveAreaM2.value ?? null;
    const radius = Number(input.radius.trim());
    // sessionStorage는 브라우저 전용이라 마운트 후 한 번만 읽는다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setKnown((prev) => ({
      summary: {
        ...prev.summary,
        address: input.roadAddress,
        floorAndUnit: input.floorUnit.trim() || '—',
        radiusM:
          input.radius.trim() && Number.isInteger(radius) && radius > 0
            ? radius
            : prev.summary.radiusM,
        exclusiveAreaText:
          area === null
            ? '확인 안 됨'
            : `약 ${Math.round(area / PYEONG_M2)}평 (${formatArea(area)})`,
      },
      floor: normalizeFloor(input.floorUnit) ?? undefined,
      exclusiveArea: area === null ? undefined : `${area}㎡`,
      parking: building?.parking.value ?? null,
    }));
  }, []);

  return known;
}

export default function AnalysisProgressPage() {
  // undefined = 아직 주소창을 읽기 전. mock 모드가 아니고 ?id=가 있으면
  // 실제 백엔드 진행 상황을 보여준다.
  const [requestId, setRequestId] = useState<string | null | undefined>();

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRequestId(
      MOCK_MODE ? null : new URLSearchParams(window.location.search).get('id')
    );
  }, []);

  if (requestId === undefined) {
    return null;
  }
  return requestId ? <LiveProgress requestId={requestId} /> : <MockProgress />;
}

/** 백엔드 없이 타이머로 흐름을 흉내 낸다(mock 모드 또는 요청 ID 없이 들어온 경우). */
function MockProgress() {
  const router = useRouter();
  const known = useKnownSite();
  const { steps, stage, resume } = useAnalysisProgressSimulation(
    mockAnalysisProgress.steps
  );
  const [demoQuestions, setDemoQuestions] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDemoQuestions(
      process.env.NODE_ENV === 'development' &&
        new URLSearchParams(window.location.search).get('demoQuestions') ===
          'alternative'
    );
  }, []);

  // 상가 정보 확인에서 주차를 이미 답했으면(가능/불가) 같은 질문을 다시 하지 않는다.
  const questions = useMemo(() => {
    const base = demoQuestions
      ? demoClarifyingQuestions
      : mockAnalysisProgress.questions;
    return known.parking === 'possible' || known.parking === 'impossible'
      ? base.filter((question) => question.questionId !== 'parking')
      : base;
  }, [demoQuestions, known.parking]);

  function handleAnswersSubmit(answers: ClarifyingAnswers, note: string) {
    // mock 단계 — 실제 제출 API 없음. ClarifyingPanel이 이미 콘솔에 기록한다.
    sessionStorage.setItem(
      'chaeum:clarifyingRecord',
      JSON.stringify({
        answers: questions
          .filter((question) => answers[question.questionId])
          .map((question) => {
            const answer = answers[question.questionId];
            return {
              label: question.shortLabel,
              answer:
                question.options.find((option) => option.id === answer.optionId)
                  ?.label ?? answer.optionId,
              detail: answer.detail,
            };
          }),
        note,
      })
    );
    resume();
  }

  return (
    <ProgressView
      steps={steps}
      stage={stage}
      questions={questions}
      summary={known.summary}
      onSubmit={handleAnswersSubmit}
      onViewReport={() => router.replace(REPORT_PATH)}
    />
  );
}

/** 실제 백엔드 진행 이벤트를 폴링한다(?id=요청 ID). */
function LiveProgress({ requestId }: { requestId: string }) {
  const router = useRouter();
  const known = useKnownSite();
  const { steps, stage, waiting, result, error, submit } = useAnalysisProgress(
    requestId,
    mockAnalysisProgress.steps
  );

  const questions = useMemo(
    () => (waiting ? toClarifyingQuestions(waiting) : []),
    [waiting]
  );
  // 층·전용면적 질문에는 앞에서 입력한 값을 미리 채운다.
  const initialAnswers = useMemo(
    () =>
      waiting
        ? prefillAnswers(waiting, {
            floor: known.floor,
            exclusiveArea: known.exclusiveArea,
          })
        : undefined,
    [waiting, known.floor, known.exclusiveArea]
  );

  // 완료되면 리포트가 읽을 수 있게 결과를 저장한다.
  useEffect(() => {
    if (result) {
      saveAnalysisResult(result);
      saveRequestId(requestId);
    }
  }, [result, requestId]);

  function handleAnswersSubmit(answers: ClarifyingAnswers) {
    // 백엔드는 질문별 답만 받는다(자유 입력 "추가 조건"을 받을 필드가 없다).
    if (waiting) {
      void submit(toAnswerSubmission(waiting, answers));
    }
  }

  return (
    <ProgressView
      steps={steps}
      stage={stage}
      questions={questions}
      initialAnswers={initialAnswers}
      questionKey={waiting?.question_session_id}
      summary={known.summary}
      error={error}
      onSubmit={handleAnswersSubmit}
      onViewReport={() => router.replace(REPORT_PATH)}
      onRestart={() => router.replace('/building-confirm')}
      showNote={false}
    />
  );
}

function ProgressView({
  steps,
  stage,
  questions,
  initialAnswers,
  questionKey,
  summary,
  error,
  onSubmit,
  onViewReport,
  onRestart,
  showNote,
}: {
  steps: ProgressStep[];
  stage: AnalysisStage;
  questions: ClarifyingQuestion[];
  initialAnswers?: ClarifyingAnswers;
  questionKey?: string;
  summary: AnalysisSummary;
  error?: string | null;
  onSubmit: (answers: ClarifyingAnswers, note: string) => void;
  onViewReport: () => void;
  onRestart?: () => void;
  showNote?: boolean;
}) {
  const copy = STAGE_COPY[stage];
  const toneColor = TONE_COLORS[copy.tone];

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="mx-auto flex w-full max-w-[1200px] flex-col items-start gap-8 px-4 pt-16 pb-24 sm:px-8">
        <div className="flex w-full flex-col items-start gap-4 sm:flex-row sm:justify-between sm:gap-6">
          <FlowPageTitle
            eyebrow="AI ANALYSIS"
            title={copy.title}
            description={copy.description}
          />

          <div
            className="flex w-full shrink-0 items-center gap-3 rounded-xl px-5 py-3.5 sm:w-auto"
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
                className="text-15 font-semibold"
                style={{
                  color:
                    copy.tone === 'waiting'
                      ? colors.accent.orange
                      : copy.tone === 'error'
                        ? colors.status.notRecommend
                        : colors.brand.dark,
                }}
              >
                {copy.statusLabel}
              </p>
              <p className="text-13" style={{ color: colors.text.secondary }}>
                {copy.statusHint}
              </p>
            </div>
          </div>
        </div>

        <StepIndicator currentStep={3} />

        {/* 넓은 화면(xl)은 3컬럼: 진행 현황 · 질문·결과 · 분석 대상.
            태블릿·작은 노트북(md~lg)은 왼쪽에 진행 현황과 분석 대상을 쌓고 오른쪽에 질문·결과.
            폰은 한 줄로, 지금 할 일이 있는 질문·결과 영역을 맨 위에 둔다. */}
        <div className="grid w-full grid-cols-1 items-start gap-4 sm:gap-6 md:grid-cols-[280px_minmax(0,1fr)] lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_300px]">
          <div className="order-2 md:order-none md:col-start-1 md:row-start-1">
            <ProgressTracker steps={steps} questionCount={questions.length} />
          </div>
          <div className="order-1 md:order-none md:col-start-2 md:row-span-2 md:row-start-1 xl:row-span-1">
            {stage === 'failed' ? (
              <FailedNotice message={error} onRestart={onRestart} />
            ) : (
              <ClarifyingPanel
                key={questionKey ?? 'none'}
                stage={stage}
                steps={steps}
                questions={questions}
                initialAnswers={initialAnswers}
                showNote={showNote}
                onSubmit={onSubmit}
                onViewReport={onViewReport}
              />
            )}
          </div>
          <div className="order-3 md:order-none md:col-start-1 md:row-start-2 xl:col-start-3 xl:row-start-1">
            <AnalysisSummaryPanel summary={summary} />
          </div>
        </div>
      </main>
    </div>
  );
}

function FailedNotice({
  message,
  onRestart,
}: {
  message?: string | null;
  onRestart?: () => void;
}) {
  return (
    <div
      className="flex w-full flex-col gap-4 rounded-3xl shadow-[0_18px_40px_rgba(16,35,58,0.06)] p-5 sm:p-8"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <p className="text-xl font-bold" style={{ color: colors.text.primary }}>
        분석을 마치지 못했어요
      </p>
      <p className="text-base" style={{ color: colors.text.secondary }}>
        {message ?? '잠시 후 다시 시도해 주세요.'}
      </p>
      {onRestart && (
        <button
          type="button"
          onClick={onRestart}
          className="w-fit rounded-lg px-5 py-3 text-base font-semibold"
          style={{
            backgroundColor: colors.brand.dark,
            color: colors.neutral.white,
          }}
        >
          다시 분석하기
        </button>
      )}
    </div>
  );
}
