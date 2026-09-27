'use client';

import { useEffect, useRef, useState } from 'react';
import type {
  ProgressPhase,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

/**
 * "데이터 수집 중" 하위 항목들은 서로 다른 외부 데이터 소스를 병렬로
 * 호출한다고 가정한 목업이라, 넷 다 동시에 시작해서 각자 다른 시간에
 * 끝난다. 실제 백엔드 진행 신호(예: 에이전트별 완료 이벤트)가 생기면
 * 이 값은 필요 없어지고 그 이벤트가 done 여부를 대신 결정한다.
 * id가 여기 없는 항목은 DEFAULT_SUB_STEP_DURATION_MS를 쓴다.
 */
const SUB_STEP_DURATIONS_MS: Record<string, number> = {
  'basic-info': 3_000,
  'commercial-area': 5_500,
  'floating-population': 7_000,
  'business-lifecycle': 9_000,
};
const DEFAULT_SUB_STEP_DURATION_MS = 5_000;

/**
 * 하위 항목이 없는 phase(AI 분석, 결과 정리) 자체의 소요 시간.
 * id가 여기 없는 phase는 DEFAULT_PHASE_DURATION_MS를 쓴다.
 */
const PHASE_DURATIONS_MS: Record<string, number> = {
  'ai-analysis': 120_000, // 최소 2분
  'result-compilation': 30_000, // 30초
};
const DEFAULT_PHASE_DURATION_MS = 60_000;

// 마운트 시 mock 데이터의 status를 그대로 쓰지 않고 전부 pending으로
// 리셋한다 — 진행 상태는 이 훅이 스스로 처음부터 만들어낸다(mock 파일의
// status 필드는 화면 모양 확인용 기본값일 뿐, 여기서는 무시된다).
function resetToPending(phases: ProgressPhase[]): ProgressPhase[] {
  return phases.map((phase) => ({
    ...phase,
    status: 'pending' as ProgressStepStatus,
    subSteps: phase.subSteps?.map((step) => ({
      ...step,
      status: 'pending' as ProgressStepStatus,
    })),
  }));
}

export function useAnalysisProgressSimulation(
  initialPhases: ProgressPhase[],
  options?: { onComplete?: () => void }
) {
  const [phases, setPhases] = useState<ProgressPhase[]>(() =>
    resetToPending(initialPhases)
  );
  // phase.id별 진행중 경과 초 — 렌더 중에는 절대 Date.now()/ref를 읽지 않고
  // (React 19 컴파일러가 금지한다), 아래 setInterval 안에서만 계산해 state로
  // 반영한다.
  const [elapsedSeconds, setElapsedSeconds] = useState<Record<string, number>>(
    {}
  );
  const onCompleteRef = useRef(options?.onComplete);
  const phaseStartedAtRef = useRef<Record<string, number>>({});
  const activePhaseIdRef = useRef<string | null>(null);

  useEffect(() => {
    onCompleteRef.current = options?.onComplete;
  }, [options?.onComplete]);

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    const tickInterval = setInterval(() => {
      const activeId = activePhaseIdRef.current;
      if (!activeId) {
        return;
      }
      const startedAt = phaseStartedAtRef.current[activeId];
      if (!startedAt) {
        return;
      }
      setElapsedSeconds({
        [activeId]: Math.floor((Date.now() - startedAt) / 1000),
      });
    }, 1000);

    function setSubStepStatus(
      phaseId: string,
      stepId: string,
      status: ProgressStepStatus
    ) {
      setPhases((prev) =>
        prev.map((phase) =>
          phase.id === phaseId
            ? {
                ...phase,
                subSteps: phase.subSteps?.map((step) =>
                  step.id === stepId ? { ...step, status } : step
                ),
              }
            : phase
        )
      );
    }

    function setPhaseStatus(phaseId: string, status: ProgressStepStatus) {
      setPhases((prev) =>
        prev.map((phase) =>
          phase.id === phaseId ? { ...phase, status } : phase
        )
      );
    }

    function markPhaseDone(phaseIndex: number) {
      setPhaseStatus(initialPhases[phaseIndex].id, 'done');
      const nextPhase = initialPhases[phaseIndex + 1];
      if (nextPhase) {
        startPhase(phaseIndex + 1);
      } else {
        activePhaseIdRef.current = null;
        clearInterval(tickInterval);
        onCompleteRef.current?.();
      }
    }

    function startPhase(phaseIndex: number) {
      const phase = initialPhases[phaseIndex];
      phaseStartedAtRef.current[phase.id] = Date.now();
      activePhaseIdRef.current = phase.id;
      setElapsedSeconds({ [phase.id]: 0 });

      if (phase.subSteps && phase.subSteps.length > 0) {
        // 병렬 시작 — 하위 항목을 전부 동시에 in_progress로 옮긴다.
        setPhases((prev) =>
          prev.map((p, i) =>
            i === phaseIndex
              ? {
                  ...p,
                  status: 'in_progress',
                  subSteps: p.subSteps?.map((step) => ({
                    ...step,
                    status: 'in_progress' as ProgressStepStatus,
                  })),
                }
              : p
          )
        );

        let remaining = phase.subSteps.length;
        phase.subSteps.forEach((step) => {
          const duration =
            SUB_STEP_DURATIONS_MS[step.id] ?? DEFAULT_SUB_STEP_DURATION_MS;
          timers.push(
            setTimeout(() => {
              setSubStepStatus(phase.id, step.id, 'done');
              remaining -= 1;
              if (remaining === 0) {
                markPhaseDone(phaseIndex);
              }
            }, duration)
          );
        });
        return;
      }

      setPhaseStatus(phase.id, 'in_progress');
      const duration =
        PHASE_DURATIONS_MS[phase.id] ?? DEFAULT_PHASE_DURATION_MS;
      timers.push(setTimeout(() => markPhaseDone(phaseIndex), duration));
    }

    startPhase(0);

    return () => {
      timers.forEach(clearTimeout);
      clearInterval(tickInterval);
    };
    // 마운트 시 한 번만 시작한다 — initialPhases는 각 항목의 id/구조를
    // 읽는 씨앗일 뿐이고, 이후 진행은 이 훅 내부 state(phases)로만 관리한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { phases, elapsedSeconds };
}
