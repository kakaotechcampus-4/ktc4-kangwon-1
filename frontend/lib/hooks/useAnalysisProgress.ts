'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AnalysisApiError,
  getAnalysis,
  getAnalysisEvents,
  submitAnswers,
} from '@/lib/api/analyses';
import {
  answerFailureAction,
  applyProgressEvent,
  toWaiting,
} from '@/lib/api/adapters/progress';
import type {
  AnswerSubmission,
  DecisionResult,
  WaitingForInput,
} from '@/lib/api/types';
import type {
  AnalysisStage,
  ProgressStep,
} from '@/lib/mockData/analysisProgress';

/**
 * 실제 백엔드 진행 상황을 폴링해 분석 진행 화면 상태를 만든다.
 * (useAnalysisProgressSimulation과 같은 steps·stage 모양을 돌려준다)
 *
 *   events 폴링 → finished면 GET /analyses/{id}로 최종 상태 확인
 *   - waiting_for_input → 질문(waiting)을 돌려주고 폴링을 멈춘다
 *   - completed → 결과(result)
 *   - failed → 오류(error)
 *   submit(답변) → POST /answers(202) → 다시 폴링
 */

// docs/API_CONTRACT.md 권장 간격: 처음 1초, 10초 뒤 2초, 1분 뒤 3초
export function pollInterval(elapsedMs: number): number {
  if (elapsedMs < 10_000) return 1_000;
  if (elapsedMs < 60_000) return 2_000;
  return 3_000;
}

// 일시적인 네트워크 오류는 몇 번 다시 시도한 뒤에만 실패로 본다.
const MAX_CONSECUTIVE_ERRORS = 5;

function markInitial(steps: ProgressStep[]): ProgressStep[] {
  return steps.map((step) => ({ ...step, status: 'pending' }));
}

export function useAnalysisProgress(
  requestId: string | null,
  initialSteps: ProgressStep[]
) {
  const [steps, setSteps] = useState<ProgressStep[]>(() =>
    markInitial(initialSteps)
  );
  const [stage, setStage] = useState<AnalysisStage>('analyzing');
  const [waiting, setWaiting] = useState<WaitingForInput | null>(null);
  const [result, setResult] = useState<DecisionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // 폴링을 다시 시작할 때마다 바뀌는 값. 이전 폴링 루프는 이 값이 달라지면 멈춘다.
  const [pollRun, setPollRun] = useState(0);
  const afterRef = useRef(0);

  useEffect(() => {
    if (!requestId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();
    let consecutiveErrors = 0;

    async function settle() {
      // 이벤트는 진행 표시용이고, 최종 상태는 GET 결과를 기준으로 한다.
      const detail = await getAnalysis(requestId as string);
      if (cancelled) return;
      if (detail.status === 'waiting_for_input' && detail.questions) {
        setWaiting(toWaiting(requestId as string, detail.questions));
        setStage('awaiting_input');
      } else if (detail.status === 'completed' && detail.result) {
        setResult(detail.result);
        setSteps((prev) => prev.map((s) => ({ ...s, status: 'done' })));
        setStage('completed');
      } else if (detail.status === 'failed') {
        setError(detail.error?.message ?? '분석에 실패했습니다.');
        setStage('failed');
      } else {
        // 아직 상태가 바뀌기 전이면 조금 뒤 다시 확인한다.
        timer = setTimeout(tick, pollInterval(Date.now() - startedAt));
      }
    }

    async function tick() {
      try {
        const page = await getAnalysisEvents(
          requestId as string,
          afterRef.current
        );
        if (cancelled) return;
        consecutiveErrors = 0;
        if (page.events.length) {
          setSteps((prev) => page.events.reduce(applyProgressEvent, prev));
          afterRef.current = page.next_after;
        }
        if (page.finished) {
          await settle();
          return;
        }
      } catch (caught) {
        if (cancelled) return;
        consecutiveErrors += 1;
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          setError(
            caught instanceof Error
              ? caught.message
              : '분석 진행 상황을 불러오지 못했습니다.'
          );
          setStage('failed');
          return;
        }
      }
      timer = setTimeout(tick, pollInterval(Date.now() - startedAt));
    }

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [requestId, pollRun]);

  /** 질문 답변을 제출하고 진행 폴링을 다시 시작한다. */
  const submit = useCallback(async (submission: AnswerSubmission) => {
    // 질문 묶음(waiting)은 지우지 않는다 — 재개 화면이 제출한 답을 요약해 보여준다.
    setSubmitError(null);
    setStage('resuming');
    try {
      await submitAnswers(submission);
      setPollRun((run) => run + 1);
    } catch (caught) {
      const status =
        caught instanceof AnalysisApiError ? caught.status : undefined;
      const action = answerFailureAction(status);
      if (action === 'resume') {
        setPollRun((run) => run + 1);
        return;
      }
      if (action === 'retry') {
        setSubmitError(
          caught instanceof AnalysisApiError
            ? caught.message
            : '답변을 보내지 못했어요. 잠시 후 다시 보내 주세요.'
        );
        setStage('awaiting_input');
        return;
      }
      setError(
        caught instanceof Error ? caught.message : '답변을 보내지 못했습니다.'
      );
      setStage('failed');
    }
  }, []);

  return { steps, stage, waiting, result, error, submitError, submit };
}
