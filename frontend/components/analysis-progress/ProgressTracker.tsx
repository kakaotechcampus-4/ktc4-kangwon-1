import { DM_Mono } from 'next/font/google';
import {
  Building2,
  Check,
  Loader2,
  Store,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { colors } from '@/styles/tokens';
import type {
  ProgressPhase,
  ProgressStep,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type ProgressTrackerProps = {
  phases: ProgressPhase[];
  // phase.id별 진행중 경과 초 — done/pending인 phase는 값이 없어도 된다.
  elapsedSeconds?: Record<string, number>;
};

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}분 ${seconds}초` : `${seconds}초`;
}

// 하위 항목 id별 아이콘 — 항목 라벨 자체는 mock 데이터가 들고 있고,
// 아이콘은 화면 표현이라 여기서만 매핑한다. 목록에 없는 id는 Building2로 대체.
const SUB_STEP_ICONS: Record<string, LucideIcon> = {
  'basic-info': Building2,
  'commercial-area': Store,
  'floating-population': Users,
  'business-lifecycle': Building2,
};

export default function ProgressTracker({
  phases,
  elapsedSeconds,
}: ProgressTrackerProps) {
  return (
    <div className="flex w-full flex-col gap-6">
      {phases.map((phase, index) => (
        <PhaseRow
          key={phase.id}
          phase={phase}
          number={index + 1}
          isLast={index === phases.length - 1}
          elapsed={elapsedSeconds?.[phase.id]}
        />
      ))}
    </div>
  );
}

function PhaseRow({
  phase,
  number,
  isLast,
  elapsed,
}: {
  phase: ProgressPhase;
  number: number;
  isLast: boolean;
  elapsed?: number;
}) {
  const isPending = phase.status === 'pending';
  const isActive = phase.status === 'in_progress';

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <StatusBadge status={phase.status} number={number} size={32} />
        {/* flex-1 라인이 오른쪽 컬럼(하위 항목 포함) 높이만큼 자동으로
            늘어난다 — flex row의 stretch 정렬 덕분에 별도 좌표 계산 없이
            다음 phase 배지까지 이어지는 타임라인을 만들 수 있다. */}
        {!isLast && (
          <div
            className="w-px flex-1"
            style={{
              backgroundColor: colors.neutral.border,
              minHeight: '16px',
            }}
          />
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4 pb-2">
        {/* relative 래퍼의 너비 = 아래 하위 항목 카드와 정확히 같은 W라서,
            여기 right-4(=하위 항목 카드의 px-4와 동일)로 앵커링한 스피너가
            카드 안 상태 아이콘과 같은 세로선 위에 정렬된다. */}
        <div className="relative">
          <div className="flex flex-col gap-1 pr-12">
            <p
              className="text-base font-semibold"
              style={{
                color: isPending
                  ? 'var(--color-gray-500)'
                  : colors.neutral.black,
              }}
            >
              {phase.title}
            </p>
            <p
              className="text-[13px]"
              style={{
                color: isPending
                  ? 'var(--color-gray-400)'
                  : 'var(--color-gray-500)',
              }}
            >
              {phase.description}
            </p>
            {isActive && elapsed !== undefined && (
              <p
                className={`${dmMono.className} text-xs`}
                style={{ color: 'var(--color-gray-400)' }}
              >
                {formatElapsed(elapsed)} 경과
              </p>
            )}
          </div>

          {/* done과 구분되는 "아직 진행 중" 신호. 아이콘 유무와 무관하게
              항상 같은 자리를 차지해야(절대 위치라 레이아웃엔 애초에
              영향 없음) 렌더링 시점에 따라 깜빡이지 않는다. */}
          <div className="absolute top-0 right-4 flex size-6 items-center justify-center">
            {isActive && (
              <Loader2
                size={24}
                className="animate-spin"
                style={{ color: colors.brand.primary }}
              />
            )}
          </div>
        </div>

        {phase.subSteps && phase.subSteps.length > 0 && (
          <div className="flex flex-col gap-2">
            {phase.subSteps.map((step) => (
              <SubStepCard key={step.id} step={step} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  number,
  size,
}: {
  status: ProgressStepStatus;
  number: number;
  size: number;
}) {
  if (status === 'done') {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full"
        style={{
          width: size,
          height: size,
          backgroundColor: colors.brand.dark,
        }}
      >
        <Check
          size={size * 0.45}
          strokeWidth={2.5}
          color={colors.neutral.white}
        />
      </div>
    );
  }

  if (status === 'in_progress') {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full text-[14px] font-semibold"
        style={{
          width: size,
          height: size,
          backgroundColor: colors.brand.dark,
          color: colors.neutral.white,
        }}
      >
        {number}
      </div>
    );
  }

  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full border text-[14px]"
      style={{
        width: size,
        height: size,
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
        color: 'var(--color-gray-400)',
      }}
    >
      {number}
    </div>
  );
}

function SubStepCard({ step }: { step: ProgressStep }) {
  const Icon = SUB_STEP_ICONS[step.id] ?? Building2;

  return (
    <div
      className="flex w-full items-center gap-3 rounded-lg border px-4 py-3.5"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <div
        className="flex size-8 shrink-0 items-center justify-center rounded-lg"
        style={{ backgroundColor: `${colors.brand.primary}1A` }}
      >
        <Icon size={16} style={{ color: colors.brand.primary }} />
      </div>

      <div className="flex flex-1 flex-col gap-0.5">
        <p
          className="text-sm font-medium"
          style={{ color: colors.neutral.black }}
        >
          {step.label}
        </p>
        <p className="text-xs" style={{ color: 'var(--color-gray-500)' }}>
          {step.description}
        </p>
      </div>

      <SubStepStatusIcon status={step.status} />
    </div>
  );
}

function SubStepStatusIcon({ status }: { status: ProgressStepStatus }) {
  if (status === 'done') {
    return (
      <div
        className="flex size-5 shrink-0 items-center justify-center rounded-full"
        style={{ backgroundColor: colors.brand.primary }}
      >
        <Check size={11} strokeWidth={3} color={colors.neutral.white} />
      </div>
    );
  }

  if (status === 'in_progress') {
    // done의 초록 체크(brand.primary)와 색이 겹치면 한눈에 구분이 안 돼서
    // 진행중 스피너는 중립 회색으로 뺀다 — "아직 끝나지 않았다"는 신호는
    // 색이 아니라 spin 애니메이션 자체로 준다.
    return (
      <Loader2
        size={18}
        className="shrink-0 animate-spin"
        style={{ color: 'var(--color-gray-300)' }}
      />
    );
  }

  return (
    <div
      className="size-5 shrink-0 rounded-full border"
      style={{ borderColor: colors.neutral.border }}
    />
  );
}
