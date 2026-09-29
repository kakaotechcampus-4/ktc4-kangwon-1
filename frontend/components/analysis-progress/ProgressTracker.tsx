import { DM_Mono } from 'next/font/google';
import { Check, Loader2, Pause } from 'lucide-react';
import Card from '@/components/ui/Card';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import type {
  ProgressStep,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type ProgressTrackerProps = {
  steps: ProgressStep[];
  // 답변 대기 단계에서 "N개 질문에 답하면…" 문구에 쓴다.
  questionCount: number;
};

// 단계 이름 뒤에 붙는 상태 문구 — "데이터 수집 완료", "추가 정보 확인 필요"처럼
// 사용자가 라벨만 읽어도 어디까지 끝났는지 알 수 있게 한다.
const STATUS_SUFFIX: Record<ProgressStepStatus, string> = {
  done: '완료',
  in_progress: '중',
  waiting: '필요',
  pending: '예정',
};

export default function ProgressTracker({
  steps,
  questionCount,
}: ProgressTrackerProps) {
  const doneCount = steps.filter((step) => step.status === 'done').length;
  const isWaiting = steps.some((step) => step.status === 'waiting');

  return (
    <Card
      className="w-full gap-6"
      style={{ padding: '26px 28px', borderRadius: '12px', borderWidth: '1px' }}
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <p
            className="text-xl font-bold"
            style={{ color: colors.text.primary }}
          >
            실시간 분석 현황
          </p>
          <p
            className={`${dmMono.className} text-sm`}
            style={{ color: colors.text.secondary }}
          >
            {doneCount} / {steps.length}
          </p>
        </div>
        <ProgressBar
          value={(doneCount / steps.length) * 100}
          color={isWaiting ? 'warning' : 'primary'}
        />
      </div>

      <ol className="flex flex-col">
        {steps.map((step, index) => (
          <StepRow
            key={step.id}
            step={step}
            isLast={index === steps.length - 1}
            questionCount={questionCount}
          />
        ))}
      </ol>
    </Card>
  );
}

/**
 * 완료·현재·예정 단계가 한눈에 갈리도록 세 단계로 무게를 나눈다.
 * - 완료: 한 발 물러난 회색 글자
 * - 현재(진행 중/답변 대기): 연한 배경 상자로 감싸 가장 먼저 눈에 띄게
 * - 예정: 옅은 회색
 */
function StepRow({
  step,
  isLast,
  questionCount,
}: {
  step: ProgressStep;
  isLast: boolean;
  questionCount: number;
}) {
  const isDone = step.status === 'done';
  const isPending = step.status === 'pending';
  const isWaiting = step.status === 'waiting';
  const isCurrent = step.status === 'in_progress' || isWaiting;
  const accent = isWaiting ? colors.accent.orange : colors.brand.primary;

  return (
    <li className="flex gap-3.5">
      <div className="flex flex-col items-center">
        <StatusIcon status={step.status} />
        {/* flex-1 라인이 오른쪽 글 높이만큼 늘어나 다음 아이콘까지 이어진다. */}
        {!isLast && (
          <div
            className="w-px flex-1"
            style={{
              backgroundColor: isDone
                ? colors.brand.primary
                : colors.neutral.border,
              minHeight: '16px',
            }}
          />
        )}
      </div>

      <div className={`flex-1 ${isLast ? '' : 'pb-5'}`}>
        <div
          // 현재 단계만 배경 상자를 두르고, 음수 마진으로 글자 위치는 다른
          // 단계와 같은 선에 맞춘다.
          className={`flex flex-col gap-1 ${
            isCurrent ? '-mt-2 rounded-lg border px-4 py-3.5' : ''
          }`}
          style={
            isCurrent
              ? {
                  backgroundColor: `${accent}12`,
                  borderColor: `${accent}59`,
                }
              : undefined
          }
        >
          <p
            className={`leading-snug ${
              isCurrent ? 'text-base font-bold' : 'text-[15px] font-medium'
            }`}
            style={{
              color: isWaiting
                ? colors.accent.orange
                : isCurrent
                  ? colors.text.primary
                  : isDone
                    ? colors.text.secondary
                    : colors.text.tertiary,
            }}
          >
            {step.label} {STATUS_SUFFIX[step.status]}
          </p>
          {isWaiting ? (
            // 왜 멈춰 있는지, 무엇을 하면 이어지는지를 설명 대신 보여준다.
            <p
              className="text-sm leading-relaxed"
              style={{ color: colors.text.secondary }}
            >
              분석이 잠시 멈춰 있어요.
              <br />
              {questionCount}개 질문에 답하면 바로 이어져요.
            </p>
          ) : (
            <p
              className="text-[13px] leading-relaxed"
              style={{
                color:
                  isDone || isPending
                    ? colors.text.tertiary
                    : colors.text.secondary,
              }}
            >
              {step.description}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function StatusIcon({ status }: { status: ProgressStepStatus }) {
  const base = 'flex size-7 shrink-0 items-center justify-center rounded-full';

  if (status === 'done') {
    return (
      // 완료는 연한 민트로 한 발 물러나게 — 진한 색은 현재 단계에만 쓴다.
      <div
        className={base}
        style={{ backgroundColor: `${colors.brand.primary}1F` }}
      >
        <Check size={15} strokeWidth={3} color={colors.brand.primary} />
      </div>
    );
  }

  if (status === 'in_progress') {
    return (
      <div
        className={base}
        style={{
          backgroundColor: colors.neutral.white,
          boxShadow: `0 0 0 2px ${colors.brand.primary}, 0 0 0 5px ${colors.brand.primary}26`,
        }}
      >
        <Loader2
          size={16}
          className="animate-spin"
          style={{ color: colors.brand.primary }}
        />
      </div>
    );
  }

  if (status === 'waiting') {
    return (
      <div
        className={base}
        style={{
          backgroundColor: colors.accent.orange,
          boxShadow: `0 0 0 4px ${colors.accent.orange}2E`,
        }}
      >
        <Pause
          size={12}
          strokeWidth={3}
          color={colors.neutral.white}
          fill={colors.neutral.white}
        />
      </div>
    );
  }

  return (
    <div
      className={`${base} border`}
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    />
  );
}
