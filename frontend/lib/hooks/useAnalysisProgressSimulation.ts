'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AnalysisStage,
  ProgressStep,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

/**
 * 분석 진행 화면의 mock 시뮬레이션.
 *
 *   데이터 수집 → (상권 · 유동인구 · 개폐업 병렬) → 추가 정보 확인(답변 대기)
 *   → 사용자가 답변 제출 → 최종 판단 → 완료
 *
 * 실제 백엔드 진행 신호(폴링/웹소켓)가 생기면 타이머 대신 그 이벤트가 각
 * 단계의 status와 stage를 결정한다. 컴포넌트는 반환값 모양에만 의존한다.
 */
const DATA_COLLECTION_ID = 'data-collection';
const CLARIFICATION_ID = 'clarification';
const DECISION_ID = 'decision';

const DATA_COLLECTION_DURATION_MS = 3_000;
// 세 분석은 서로 다른 데이터 소스를 병렬로 본다고 가정해 동시에 시작하고
// 각자 다른 시간에 끝난다.
const PARALLEL_ANALYSIS_DURATIONS_MS: Record<string, number> = {
  'commercial-area': 4_000,
  'floating-population': 5_500,
  'business-lifecycle': 7_000,
};
const DECISION_DURATION_MS = 8_000;

// 마운트 시 mock 데이터의 status는 무시하고 첫 단계만 진행 중으로 시작한다.
function toInitialSteps(steps: ProgressStep[]): ProgressStep[] {
  return steps.map((step) => ({
    ...step,
    status: (step.id === DATA_COLLECTION_ID
      ? 'in_progress'
      : 'pending') as ProgressStepStatus,
  }));
}

export function useAnalysisProgressSimulation(
  initialSteps: ProgressStep[],
  options?: { onComplete?: () => void }
) {
  const [steps, setSteps] = useState<ProgressStep[]>(() =>
    toInitialSteps(initialSteps)
  );
  const [stage, setStage] = useState<AnalysisStage>('analyzing');
  const onCompleteRef = useRef(options?.onComplete);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    onCompleteRef.current = options?.onComplete;
  }, [options?.onComplete]);

  const setStatus = useCallback((ids: string[], status: ProgressStepStatus) => {
    setSteps((prev) =>
      prev.map((step) => (ids.includes(step.id) ? { ...step, status } : step))
    );
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    const parallelIds = Object.keys(PARALLEL_ANALYSIS_DURATIONS_MS);

    timers.push(
      setTimeout(() => {
        setStatus([DATA_COLLECTION_ID], 'done');
        setStatus(parallelIds, 'in_progress');

        let remaining = parallelIds.length;
        parallelIds.forEach((id) => {
          timers.push(
            setTimeout(() => {
              setStatus([id], 'done');
              remaining -= 1;
              if (remaining === 0) {
                // 분석 중 판단에 필요한 정보가 부족하다는 걸 발견한 시점.
                setStatus([CLARIFICATION_ID], 'waiting');
                setStage('awaiting_input');
              }
            }, PARALLEL_ANALYSIS_DURATIONS_MS[id])
          );
        });
      }, DATA_COLLECTION_DURATION_MS)
    );

    return () => {
      timers.forEach(clearTimeout);
      timers.length = 0;
    };
  }, [setStatus]);

  // 사용자가 답변을 제출하면 멈춰 있던 분석을 이어간다.
  const resume = useCallback(() => {
    setStatus([CLARIFICATION_ID], 'done');
    setStatus([DECISION_ID], 'in_progress');
    setStage('resuming');

    timersRef.current.push(
      setTimeout(() => {
        setStatus([DECISION_ID], 'done');
        setStage('completed');
        onCompleteRef.current?.();
      }, DECISION_DURATION_MS)
    );
  }, [setStatus]);

  return { steps, stage, resume };
}
