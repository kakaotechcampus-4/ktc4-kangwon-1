'use client';

import { useState } from 'react';
import { DM_Mono } from 'next/font/google';
import { Check, ChevronDown, Info, Loader2 } from 'lucide-react';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import type {
  AnalysisStage,
  ClarifyingQuestion,
  ProgressStep,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

type ClarifyingPanelProps = {
  stage: AnalysisStage;
  steps: ProgressStep[];
  questions: ClarifyingQuestion[];
  onSubmit: (answers: Record<string, string>, note: string) => void;
  onViewReport: () => void;
};

/**
 * 화면 중앙 영역. 채팅이 아니라 "분석을 이어가기 위한 확인 양식"으로 보이게
 * 만든다 — 말풍선·타임스탬프 없이 번호 붙은 질문 카드와 진행률만 둔다.
 * stage에 따라 분석 중 안내 → 질문 양식 → 분석 재개 안내로 모양이 바뀐다.
 */
export default function ClarifyingPanel({
  stage,
  steps,
  questions,
  onSubmit,
  onViewReport,
}: ClarifyingPanelProps) {
  // 답변/입력값은 로컬 state로만 관리한다 — 실제 제출 API는 아직 없다.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [note, setNote] = useState('');

  if (stage === 'analyzing') {
    return <AnalyzingOverview steps={steps} />;
  }

  if (stage === 'resuming' || stage === 'completed') {
    return (
      <ResumingPanel
        questions={questions}
        answers={answers}
        note={note}
        isCompleted={stage === 'completed'}
        onViewReport={onViewReport}
      />
    );
  }

  const answeredCount = questions.filter(
    (question) => answers[question.questionId]
  ).length;
  const remaining = questions.length - answeredCount;
  const canSubmit = remaining === 0;

  function handleSubmit() {
    // mock 처리 — 실제 API 연동 없이 콘솔에만 기록한다.
    console.log('[ClarifyingPanel] 답변 제출(mock):', { answers, note });
    onSubmit(answers, note);
  }

  // 외곽 카드 없이 제목·진행률 → 질문 카드들 → 추가 입력 순으로 바로 놓는다.
  // 질문 카드가 이 영역에서 유일한 카드라서 질문이 가장 먼저 눈에 들어온다.
  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-3">
        <div className="flex items-end justify-between gap-4">
          <h2
            className="text-[22px] leading-snug font-bold"
            style={{ color: colors.text.primary }}
          >
            분석을 위해 {questions.length}가지 확인이 필요해요
          </h2>
          <p
            className="shrink-0 text-[15px] font-semibold"
            style={{ color: colors.brand.dark }}
          >
            <span className={dmMono.className}>
              {answeredCount} / {questions.length}
            </span>{' '}
            답변 완료
          </p>
        </div>
        <ProgressBar value={(answeredCount / questions.length) * 100} />
      </div>

      <div className="flex flex-col gap-4">
        {questions.map((question, index) => (
          <QuestionCard
            key={question.questionId}
            number={index + 1}
            question={question}
            selected={answers[question.questionId]}
            onSelect={(option) =>
              setAnswers((prev) => ({
                ...prev,
                [question.questionId]: option,
              }))
            }
          />
        ))}
      </div>

      <label className="flex flex-col gap-2">
        <span
          className="text-sm font-semibold"
          style={{ color: colors.text.secondary }}
        >
          추가로 알려주실 내용 <span className="font-normal">(선택)</span>
        </span>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={2}
          placeholder="예: 2층까지 함께 임대 가능해요"
          className="w-full resize-none rounded-lg border px-4 py-3 text-[15px] leading-relaxed placeholder:text-gray-400"
          style={{
            borderColor: colors.neutral.border,
            backgroundColor: colors.neutral.white,
            color: colors.text.primary,
          }}
        />
      </label>

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="primary"
          className="min-h-[52px] w-full justify-center disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:opacity-40"
          // Button 기본 text-sm이 클래스보다 우선 적용돼 글자 크기는 style로 준다.
          style={{ fontSize: '16px' }}
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          답변하고 분석 이어가기 →
        </Button>
        <p
          className="text-center text-[13px] leading-relaxed"
          style={{ color: colors.text.secondary }}
        >
          {canSubmit
            ? '제출하면 답변을 반영해 최종 판단을 시작해요.'
            : `남은 질문 ${remaining}개에 답하면 분석을 이어갈 수 있어요. 잘 모르시면 '모르겠어요'를 골라도 괜찮아요.`}
        </p>
      </div>
    </section>
  );
}

function QuestionCard({
  number,
  question,
  selected,
  onSelect,
}: {
  number: number;
  question: ClarifyingQuestion;
  selected?: string;
  onSelect: (option: string) => void;
}) {
  const [isReasonOpen, setIsReasonOpen] = useState(false);
  const isAnswered = Boolean(selected);
  const reasonId = `reason-${question.questionId}`;

  return (
    <div
      className="flex flex-col gap-5 rounded-xl border p-6"
      style={{
        borderColor: isAnswered
          ? `${colors.brand.primary}66`
          : colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className={`${dmMono.className} flex size-8 shrink-0 items-center justify-center rounded-full text-[13px] font-medium`}
          style={
            isAnswered
              ? {
                  backgroundColor: colors.brand.primary,
                  color: colors.neutral.white,
                }
              : {
                  backgroundColor: colors.neutral.background,
                  color: colors.brand.dark,
                }
          }
        >
          {isAnswered ? <Check size={16} strokeWidth={3} /> : `Q${number}`}
        </div>
        <div className="flex flex-1 flex-col gap-1.5 pt-0.5">
          <p
            className="text-lg leading-snug font-semibold"
            style={{ color: colors.text.primary }}
          >
            {question.question}
          </p>
          <p
            className="text-sm leading-relaxed"
            style={{ color: colors.text.secondary }}
          >
            {question.context}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2.5 pl-11">
        {question.options.map((option) => {
          const isSelected = selected === option;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(option)}
              className="min-h-[44px] rounded-lg border px-5 py-2.5 text-[15px]"
              style={{
                borderColor: isSelected
                  ? colors.brand.dark
                  : colors.neutral.border,
                backgroundColor: isSelected
                  ? `${colors.brand.primary}14`
                  : colors.neutral.white,
                color: isSelected ? colors.brand.dark : colors.text.secondary,
                fontWeight: isSelected ? 600 : 500,
              }}
            >
              {option}
            </button>
          );
        })}
      </div>

      <div className="flex flex-col gap-2.5 pl-11">
        <button
          type="button"
          aria-expanded={isReasonOpen}
          aria-controls={reasonId}
          onClick={() => setIsReasonOpen((prev) => !prev)}
          className="flex w-fit items-center gap-1 text-sm font-semibold"
          style={{ color: colors.brand.primary }}
        >
          <Info size={15} />왜 필요한가요?
          <ChevronDown
            size={15}
            className={`transition-transform ${isReasonOpen ? 'rotate-180' : ''}`}
          />
        </button>
        {isReasonOpen && (
          <p
            id={reasonId}
            className="rounded-lg px-4 py-3.5 text-sm leading-relaxed"
            style={{
              backgroundColor: `${colors.brand.primary}0F`,
              color: colors.text.secondary,
            }}
          >
            {question.reason}
          </p>
        )}
      </div>
    </div>
  );
}

// 분석 중 화면에서 보여줄 분석 항목 — 좌측 단계 라벨과 겹치지 않게
// "무엇을 보고 있는지"를 짧은 말로 바꿔 쓴다.
const ANALYSIS_FOCUS: { stepId: string; label: string }[] = [
  { stepId: 'commercial-area', label: '상권 경쟁도' },
  { stepId: 'floating-population', label: '유동인구 패턴' },
  { stepId: 'business-lifecycle', label: '개폐업 추이' },
];

// 질문이 생기기 전 — 빈 로딩 화면처럼 보이지 않게 지금 도는 분석만 가볍게 보여준다.
function AnalyzingOverview({ steps }: { steps: ProgressStep[] }) {
  const statusById = new Map(steps.map((step) => [step.id, step.status]));
  const focus = ANALYSIS_FOCUS.map((item) => ({
    ...item,
    status: statusById.get(item.stepId) ?? 'pending',
  }));
  const runningCount = focus.filter(
    (item) => item.status === 'in_progress'
  ).length;

  return (
    <Card
      className="w-full items-center gap-6 text-center"
      style={{ padding: '48px 36px', borderRadius: '12px', borderWidth: '1px' }}
    >
      <div className="flex flex-col items-center gap-3">
        <Loader2
          size={28}
          className="animate-spin"
          style={{ color: colors.brand.primary }}
        />
        <p className="text-xl font-bold" style={{ color: colors.text.primary }}>
          자료를 모아 분석하고 있어요
        </p>
        <p className="text-[15px]" style={{ color: colors.text.secondary }}>
          {runningCount > 0
            ? `현재 ${runningCount}개의 분석이 진행 중이에요`
            : '주변 자료를 모은 뒤 3가지 분석을 동시에 시작해요'}
        </p>
      </div>

      <ul className="flex flex-wrap justify-center gap-2.5">
        {focus.map((item) => (
          <FocusChip
            key={item.stepId}
            label={item.label}
            status={item.status}
          />
        ))}
      </ul>

      <p className="text-[13px]" style={{ color: colors.text.tertiary }}>
        판단에 필요한 정보가 부족하면 이 자리에서 여쭤볼게요.
      </p>
    </Card>
  );
}

function FocusChip({
  label,
  status,
}: {
  label: string;
  status: ProgressStepStatus;
}) {
  const isRunning = status === 'in_progress';
  const isDone = status === 'done';

  return (
    <li
      className="flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium"
      style={{
        borderColor: isRunning
          ? `${colors.brand.primary}66`
          : colors.neutral.border,
        backgroundColor: isRunning
          ? `${colors.brand.primary}0F`
          : colors.neutral.white,
        color: isRunning || isDone ? colors.brand.dark : colors.text.tertiary,
      }}
    >
      {isRunning && (
        <Loader2
          size={14}
          className="animate-spin"
          style={{ color: colors.brand.primary }}
        />
      )}
      {isDone && (
        <Check
          size={14}
          strokeWidth={3}
          style={{ color: colors.brand.primary }}
        />
      )}
      {label}
    </li>
  );
}

// 답변 제출 후 — 답변 확인이 아니라 "분석이 다시 돌고 있다"가 주인공이다.
// 답변은 작은 요약으로만 두고, 하단에 지금 계산 중인 내용을 보여준다.
function ResumingPanel({
  questions,
  answers,
  note,
  isCompleted,
  onViewReport,
}: {
  questions: ClarifyingQuestion[];
  answers: Record<string, string>;
  note: string;
  isCompleted: boolean;
  onViewReport: () => void;
}) {
  const summaryRows = [
    ...questions.map((question) => ({
      label: question.shortLabel,
      value: answers[question.questionId],
    })),
    ...(note ? [{ label: '추가 조건', value: note }] : []),
  ];

  return (
    <Card
      className="w-full gap-6"
      style={{ padding: '28px', borderRadius: '12px', borderWidth: '1px' }}
    >
      <div className="flex items-start gap-3.5">
        <div
          className="flex size-11 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: `${colors.brand.primary}1A` }}
        >
          {isCompleted ? (
            <Check
              size={22}
              strokeWidth={3}
              style={{ color: colors.brand.primary }}
            />
          ) : (
            <Loader2
              size={22}
              className="animate-spin"
              style={{ color: colors.brand.primary }}
            />
          )}
        </div>
        <div className="flex flex-col gap-1">
          <h2
            className="text-[22px] leading-snug font-bold"
            style={{ color: colors.text.primary }}
          >
            {isCompleted
              ? '분석을 마쳤어요'
              : '답변을 반영해 분석을 이어가고 있어요'}
          </h2>
          <p
            className="text-[15px] leading-relaxed"
            style={{ color: colors.text.secondary }}
          >
            {isCompleted
              ? '아래 버튼을 눌러 맞춤 리포트를 확인해 보세요.'
              : '알려주신 조건을 넣어 추천·비추천 업종을 다시 계산하는 중이에요.'}
          </p>
        </div>
      </div>

      <div
        className="flex flex-col gap-3 rounded-lg px-5 py-4"
        style={{ backgroundColor: colors.neutral.background }}
      >
        <p
          className="flex items-center gap-1.5 text-sm font-semibold"
          style={{ color: colors.brand.primary }}
        >
          <Check size={15} strokeWidth={3} />
          답변 반영 완료
        </p>
        <dl className="flex flex-col gap-2">
          {summaryRows.map((row) => (
            <div key={row.label} className="flex items-start gap-4 text-[15px]">
              <dt
                className="w-[104px] shrink-0"
                style={{ color: colors.text.tertiary }}
              >
                {row.label}
              </dt>
              <dd
                className="font-medium"
                style={{ color: colors.text.primary }}
              >
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      {isCompleted ? (
        <Button
          type="button"
          variant="primary"
          // 이 화면의 마지막이자 가장 중요한 액션 — 다른 버튼보다 한 단계 크게.
          className="min-h-[56px] w-full justify-center"
          style={{ fontSize: '16px' }}
          onClick={onViewReport}
        >
          리포트 보기 →
        </Button>
      ) : (
        <div className="flex flex-col gap-2.5">
          <p
            className="text-[15px] font-semibold"
            style={{ color: colors.brand.dark }}
          >
            최종 업종 적합도를 계산하고 있어요...
          </p>
          {/* 실제 진행률을 모르는 구간이라 채움 비율 대신 움직임으로만 알린다. */}
          <div
            className="h-2 w-full overflow-hidden rounded-full"
            style={{ backgroundColor: colors.neutral.border }}
          >
            <div
              className="animate-indeterminate h-full w-2/5 rounded-full"
              style={{ backgroundColor: colors.brand.primary }}
            />
          </div>
        </div>
      )}
    </Card>
  );
}
