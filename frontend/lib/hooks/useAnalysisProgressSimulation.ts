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
 *   주소 확인 → 자료 조회·채점 → 업종 판단 → 추가 정보 확인(답변 대기)
 *   → 사용자가 답변 제출 → 업종 판단 마무리 → 평가자 검토 → 최종 리포트 → 완료
 *
 * 실제 백엔드 진행 이벤트를 쓰는 화면은 useAnalysisProgress가 같은 모양을 돌려준다.
 */
const ADDRESS_ID = 'address';
const LOCAL_DATA_ID = 'local-data';
const DECISION_ID = 'decision';
const CLARIFICATION_ID = 'clarification';
const EVALUATION_ID = 'evaluation';
const REPORT_ID = 'report';

// 질문 전까지 차례로 끝나는 단계와 각 소요 시간
const BEFORE_QUESTION_MS: [string, number][] = [
  [ADDRESS_ID, 2_000],
  [LOCAL_DATA_ID, 4_000],
];
// 업종 판단을 시작하고 질문이 생기기까지
const UNTIL_QUESTION_MS = 4_000;
// 답변 뒤 차례로 끝나는 단계와 각 소요 시간
const AFTER_QUESTION_MS: [string, number][] = [
  [DECISION_ID, 3_000],
  [EVALUATION_ID, 4_000],
  [REPORT_ID, 3_000],
];

// 마운트 시 mock 데이터의 status는 무시하고 첫 단계만 진행 중으로 시작한다.
function toInitialSteps(steps: ProgressStep[]): ProgressStep[] {
  return steps.map((step) => ({
    ...step,
    status: (step.id === ADDRESS_ID
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

  // 단계를 하나씩 진행 중 → 완료로 넘기고, 다 끝나면 onDone을 부른다.
  const runSequence = useCallback(
    (sequence: [string, number][], onDone: () => void) => {
      let delay = 0;
      sequence.forEach(([id, duration], index) => {
        timersRef.current.push(
          setTimeout(() => setStatus([id], 'in_progress'), delay)
        );
        delay += duration;
        timersRef.current.push(
          setTimeout(() => {
            setStatus([id], 'done');
            if (index === sequence.length - 1) {
              onDone();
            }
          }, delay)
        );
      });
    },
    [setStatus]
  );

  useEffect(() => {
    const timers = timersRef.current;
    runSequence(BEFORE_QUESTION_MS, () => {
      setStatus([DECISION_ID], 'in_progress');
      timers.push(
        setTimeout(() => {
          // 판단 중 필요한 정보가 부족하다는 걸 발견한 시점.
          setStatus([DECISION_ID], 'pending');
          setStatus([CLARIFICATION_ID], 'waiting');
          setStage('awaiting_input');
        }, UNTIL_QUESTION_MS)
      );
    });

    return () => {
      timers.forEach(clearTimeout);
      timers.length = 0;
    };
  }, [runSequence, setStatus]);

  // 사용자가 답변을 제출하면 멈춰 있던 분석을 이어간다.
  const resume = useCallback(() => {
    setStatus([CLARIFICATION_ID], 'done');
    setStage('resuming');
    runSequence(AFTER_QUESTION_MS, () => {
      setStage('completed');
      onCompleteRef.current?.();
    });
  }, [runSequence, setStatus]);

  return { steps, stage, resume };
}
