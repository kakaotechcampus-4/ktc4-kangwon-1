import type {
  AnalysisEvent,
  AnswerSubmission,
  LandlordAnswer,
  QuestionField,
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
 * (이벤트 정의: docs/API_CONTRACT.md "GET /api/v1/analyses/{request_id}/events")
 */

// 화면의 6단계 id
const STEP = {
  data: 'data-collection',
  commercial: 'commercial-area',
  floating: 'floating-population',
  lifecycle: 'business-lifecycle',
  clarification: 'clarification',
  decision: 'decision',
} as const;

const AGENT_STEP: Record<string, string> = {
  commercial_area: STEP.commercial,
  floating_population: STEP.floating,
  business_lifecycle: STEP.lifecycle,
};

// 최종판단 중에 일어나는 보조 작업 — 화면에서는 "최종 판단 중"으로 묶는다.
const DECISION_SIDE_STAGES = ['supplement', 'map', 'brief.', 'consult.'];

function setStatus(
  steps: ProgressStep[],
  id: string,
  status: ProgressStepStatus
): ProgressStep[] {
  return steps.map((step) => (step.id === id ? { ...step, status } : step));
}

function statusOf(steps: ProgressStep[], id: string) {
  return steps.find((step) => step.id === id)?.status;
}

/** 이벤트 하나를 반영한 새 단계 목록. 알 수 없는 이벤트는 무시한다. */
export function applyProgressEvent(
  steps: ProgressStep[],
  event: AnalysisEvent
): ProgressStep[] {
  const { stage, event: name, detail } = event;

  if (stage === 'address') {
    return setStatus(
      steps,
      STEP.data,
      name === 'completed' ? 'done' : 'in_progress'
    );
  }
  if (stage in AGENT_STEP) {
    // 에이전트가 시작되면 주소·자료 준비는 끝난 것이다.
    const next = setStatus(steps, STEP.data, 'done');
    return setStatus(
      next,
      AGENT_STEP[stage],
      name === 'completed' ? 'done' : 'in_progress'
    );
  }
  if (stage === 'questions' && name === 'waiting') {
    return setStatus(
      setStatus(steps, STEP.clarification, 'waiting'),
      STEP.decision,
      'pending'
    );
  }
  if (stage === 'decision') {
    if (name === 'started') {
      // 답변을 받고 다시 판단을 시작했다면 질문 단계는 끝난 것이다.
      const next =
        statusOf(steps, STEP.clarification) === 'waiting'
          ? setStatus(steps, STEP.clarification, 'done')
          : steps;
      return setStatus(next, STEP.decision, 'in_progress');
    }
    if (name === 'completed') {
      // action이 final이 아니면(질문·보완·되묻기) 판단이 이어진다.
      return detail.action === 'final'
        ? setStatus(steps, STEP.decision, 'done')
        : steps;
    }
  }
  if (DECISION_SIDE_STAGES.some((prefix) => stage.startsWith(prefix))) {
    return setStatus(steps, STEP.decision, 'in_progress');
  }
  if (stage === 'run' && name === 'completed') {
    // 질문 없이 끝나도 모든 단계를 완료로 표시한다.
    return steps.map((step) => ({ ...step, status: 'done' }));
  }
  return steps;
}

// ---------------------------------------------------------------------------
// 질문·답변
// ---------------------------------------------------------------------------

const FIELD_LABELS: Record<QuestionField, string> = {
  floor: '층',
  exclusive_area: '전용면적',
  space_condition: '공간 상태',
  existing_facilities: '기존 설비',
  industry_preferences: '원하는 업종',
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

/** 백엔드 질문을 질문 카드로 바꾼다. 답은 자유 입력 + 모르겠어요 + 건너뛰기. */
export function toClarifyingQuestions(
  waiting: WaitingForInput
): ClarifyingQuestion[] {
  return waiting.questions.map((question) => ({
    questionId: question.field,
    question: question.text,
    shortLabel: FIELD_LABELS[question.field] ?? question.field,
    context: question.expected_impact,
    reason: question.why_needed,
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
  return {
    request_id: waiting.request_id,
    question_set_id: waiting.question_set_id,
    answers: waiting.questions.map(({ field }): LandlordAnswer => {
      const answer = answers[field];
      const value = answer?.detail?.trim();
      if (answer?.optionId === ANSWERED_OPTION_ID && value) {
        return { field, status: 'answered', value: value.slice(0, 1000) };
      }
      if (answer?.optionId === UNKNOWN_OPTION_ID) {
        return { field, status: 'unknown' };
      }
      return { field, status: 'skipped' };
    }),
  };
}
