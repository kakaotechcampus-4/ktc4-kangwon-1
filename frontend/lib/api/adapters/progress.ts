import type {
  AnalysisEvent,
  AnswerSubmission,
  QuestionField,
  StoredQuestions,
  WaitingForInput,
} from '@/lib/api/types';
import type {
  ClarifyingAnswers,
  ClarifyingQuestion,
  ProgressStep,
  ProgressStepStatus,
} from '@/lib/mockData/analysisProgress';

/**
 * 백엔드 진행 이벤트·질문을 분석 진행 화면의 데이터 모양으로 바꾼다.
 * 화면 컴포넌트는 mock 시뮬레이션과 같은 모양(steps, ClarifyingQuestion)만 받는다.
 * (이벤트 정의: docs/API_CONTRACT.md "진행 이벤트 stage 변경")
 *
 *   address → local_data → decision(도구 호출마다) → [question waiting]
 *   → evaluation(평가자 네 명) → final
 */

// 화면의 6단계 id — lib/mockData/analysisProgress.ts steps와 같다.
export const STEP = {
  address: 'address',
  localData: 'local-data',
  decision: 'decision',
  clarification: 'clarification',
  evaluation: 'evaluation',
  report: 'report',
} as const;

function setStatus(
  steps: ProgressStep[],
  ids: string[],
  status: ProgressStepStatus
): ProgressStep[] {
  return steps.map((step) =>
    ids.includes(step.id) ? { ...step, status } : step
  );
}

function statusOf(steps: ProgressStep[], id: string) {
  return steps.find((step) => step.id === id)?.status;
}

/** 이벤트 하나를 반영한 새 단계 목록. 알 수 없는 이벤트는 무시한다. */
export function applyProgressEvent(
  steps: ProgressStep[],
  event: AnalysisEvent
): ProgressStep[] {
  const { stage, event: name } = event;
  const done = name === 'completed';

  if (stage === 'address') {
    return setStatus(steps, [STEP.address], done ? 'done' : 'in_progress');
  }
  if (stage === 'local_data') {
    // 자료 조회가 시작됐다면 주소 확인은 끝난 것이다.
    const next = setStatus(steps, [STEP.address], 'done');
    return setStatus(next, [STEP.localData], done ? 'done' : 'in_progress');
  }
  if (stage === 'decision') {
    // decision completed는 도구 호출 하나가 끝났다는 뜻이라 판단은 계속된다.
    // 답변 뒤 다시 판단을 시작했다면 질문 단계는 끝난 것이다.
    const next =
      statusOf(steps, STEP.clarification) === 'waiting'
        ? setStatus(steps, [STEP.clarification], 'done')
        : steps;
    return setStatus(
      setStatus(next, [STEP.address, STEP.localData], 'done'),
      [STEP.decision],
      'in_progress'
    );
  }
  if (stage === 'question' && name === 'waiting') {
    return setStatus(
      setStatus(steps, [STEP.decision], 'pending'),
      [STEP.clarification],
      'waiting'
    );
  }
  if (stage === 'evaluation') {
    // 평가자 검토는 업종 판단 초안이 나온 뒤에 시작한다.
    const next = setStatus(
      steps,
      [STEP.address, STEP.localData, STEP.decision],
      'done'
    );
    return statusOf(next, STEP.evaluation) === 'done'
      ? next
      : setStatus(next, [STEP.evaluation], 'in_progress');
  }
  if (stage === 'final') {
    if (name === 'started') {
      return setStatus(
        setStatus(
          steps,
          [STEP.address, STEP.localData, STEP.decision, STEP.evaluation],
          'done'
        ),
        [STEP.report],
        'in_progress'
      );
    }
    if (done) {
      // 질문 없이 끝나도 모든 단계를 완료로 표시한다.
      return steps.map((step) => ({ ...step, status: 'done' }));
    }
  }
  return steps;
}

// ---------------------------------------------------------------------------
// 질문·답변
// ---------------------------------------------------------------------------

/** GET /analyses/{id}의 질문 칸을 화면이 쓰는 WaitingForInput 하나로 맞춘다. */
export function toWaiting(
  requestId: string,
  stored: StoredQuestions
): WaitingForInput {
  return {
    status: 'waiting_for_input',
    request_id: requestId,
    question_session_id: stored.question_session_id,
    questions: stored.questions,
  };
}

const FIELD_LABELS: Record<QuestionField, string> = {
  floor: '층',
  exclusive_area: '전용면적',
  space_condition: '공간 상태',
  existing_facilities: '기존 설비',
  industry_preferences: '원하는 업종',
};

const FIELD_HINTS: Record<QuestionField, string> = {
  floor: '상가가 있는 층을 알려주세요.',
  exclusive_area: '실제로 쓰는 면적을 알려주세요.',
  space_condition: '지금 공간이 어떤 상태인지 알려주세요.',
  existing_facilities: '남아 있는 설비를 알려주세요.',
  industry_preferences: '원하거나 피하고 싶은 업종을 알려주세요.',
};

const FIELD_PLACEHOLDERS: Record<QuestionField, string> = {
  floor: '예: 1층',
  exclusive_area: '예: 85㎡',
  space_condition: '예: 철거 완료, 바닥 공사 필요',
  existing_facilities: '예: 급배수 있음, 환기구 없음',
  industry_preferences: '예: 카페나 학원을 원해요',
};

export const ANSWERED_OPTION_ID = 'answered';
const UNKNOWN_OPTION_ID = 'unknown';
const SKIPPED_OPTION_ID = 'skipped';

// 백엔드는 모든 질문에 비어 있지 않은 답을 받는다. 고르지 않은 선택지도
// 판단 모델이 읽을 수 있게 문장으로 보낸다.
export const UNKNOWN_ANSWER = '모르겠습니다.';
export const SKIPPED_ANSWER = '답변하지 않았습니다.';
const MAX_ANSWER_LENGTH = 500;

/** 백엔드 질문을 질문 카드로 바꾼다. 답은 자유 입력 + 모르겠어요 + 건너뛰기. */
export function toClarifyingQuestions(
  waiting: WaitingForInput
): ClarifyingQuestion[] {
  return waiting.questions.map((question) => ({
    questionId: question.field,
    question: question.question,
    shortLabel: FIELD_LABELS[question.field] ?? question.field,
    context: FIELD_HINTS[question.field] ?? '',
    reason: question.reason,
    options: [
      {
        id: ANSWERED_OPTION_ID,
        label: '직접 입력',
        detailInput: {
          label: '답변',
          placeholder: FIELD_PLACEHOLDERS[question.field],
          required: true,
        },
      },
      { id: UNKNOWN_OPTION_ID, label: '모르겠어요' },
      { id: SKIPPED_OPTION_ID, label: '건너뛰기' },
    ],
  }));
}

/**
 * 앞 단계에서 이미 받은 값(층, 전용면적)을 해당 질문의 답으로 미리 채운다.
 * 사용자는 질문 화면에서 그대로 내거나 고칠 수 있다.
 */
export function prefillAnswers(
  waiting: WaitingForInput,
  known: { floor?: string; exclusiveArea?: string }
): ClarifyingAnswers {
  const prefilled: ClarifyingAnswers = {};
  for (const { field } of waiting.questions) {
    const value =
      field === 'floor'
        ? known.floor
        : field === 'exclusive_area'
          ? known.exclusiveArea
          : undefined;
    if (value?.trim()) {
      prefilled[field] = { optionId: ANSWERED_OPTION_ID, detail: value.trim() };
    }
  }
  return prefilled;
}

/** 질문 카드의 답을 백엔드 제출 형식으로 바꾼다. 고르지 않은 질문은 건너뛰기로 보낸다. */
export function toAnswerSubmission(
  waiting: WaitingForInput,
  answers: ClarifyingAnswers
): AnswerSubmission {
  const submitted: AnswerSubmission['answers'] = {};
  for (const { field } of waiting.questions) {
    const answer = answers[field];
    const value = answer?.detail?.trim();
    submitted[field] =
      answer?.optionId === ANSWERED_OPTION_ID && value
        ? value.slice(0, MAX_ANSWER_LENGTH)
        : answer?.optionId === UNKNOWN_OPTION_ID
          ? UNKNOWN_ANSWER
          : SKIPPED_ANSWER;
  }
  return {
    request_id: waiting.request_id,
    question_session_id: waiting.question_session_id,
    answers: submitted,
  };
}

export function progressView({
  mockMode,
  requestId,
}: {
  mockMode: boolean;
  requestId: string | null;
}): 'live' | 'mock' | 'none' {
  if (mockMode) {
    return 'mock';
  }
  return requestId ? 'live' : 'none';
}

export function answerFailureAction(
  status: number | undefined
): 'resume' | 'retry' | 'fail' {
  if (status === 409) {
    return 'resume';
  }
  if (
    status === undefined ||
    status === 408 ||
    status === 429 ||
    status >= 500
  ) {
    return 'retry';
  }
  return 'fail';
}
