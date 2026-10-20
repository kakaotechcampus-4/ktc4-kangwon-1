import { describe, expect, it } from 'vitest';
import {
  ANSWERED_OPTION_ID,
  SKIPPED_ANSWER,
  UNKNOWN_ANSWER,
  applyProgressEvent,
  prefillAnswers,
  toAnswerSubmission,
  toClarifyingQuestions,
  toWaiting,
} from './progress';
import { pollInterval } from '@/lib/hooks/useAnalysisProgress';
import { mockAnalysisProgress } from '@/lib/mockData/analysisProgress';
import type { AnalysisEvent, WaitingForInput } from '@/lib/api/types';

const initial = mockAnalysisProgress.steps.map((step) => ({
  ...step,
  status: 'pending' as const,
}));

let seq = 0;
function ev(
  stage: string,
  event: string,
  detail: Record<string, unknown> = {}
): AnalysisEvent {
  seq += 1;
  return { seq, at: '2026-10-12T00:00:00+00:00', stage, event, detail };
}

function statuses(events: AnalysisEvent[]) {
  const steps = events.reduce(applyProgressEvent, initial);
  return Object.fromEntries(steps.map((step) => [step.id, step.status]));
}

const waiting: WaitingForInput = {
  status: 'waiting_for_input',
  request_id: 'req-1',
  question_session_id: 'qs-1',
  questions: [
    {
      field: 'floor',
      question: '몇 층인가요?',
      reason: '층에 따라 가능한 업종이 다릅니다.',
    },
    {
      field: 'space_condition',
      question: '공간 상태는 어떤가요?',
      reason: '공사 범위를 판단합니다.',
    },
  ],
};

describe('applyProgressEvent', () => {
  it('자료 조회가 시작되면 주소 확인을 끝내고 조회를 진행 중으로 둔다', () => {
    const result = statuses([
      ev('address', 'started'),
      ev('local_data', 'started'),
    ]);
    expect(result.address).toBe('done');
    expect(result['local-data']).toBe('in_progress');
    expect(result.decision).toBe('pending');
  });

  it('도구 호출이 끝나도 판단은 계속 진행 중이다', () => {
    const result = statuses([
      ev('local_data', 'completed'),
      ev('decision', 'completed', { tool: 'get_scorecard', status: 'ok' }),
    ]);
    expect(result['local-data']).toBe('done');
    expect(result.decision).toBe('in_progress');
  });

  it('질문 대기 뒤 판단이 다시 오면 질문 단계를 끝낸다', () => {
    const asked = [
      ev('decision', 'completed', { tool: 'ask_user', status: 'ok' }),
      ev('question', 'waiting', { question_session_id: 'qs-1' }),
    ];
    expect(statuses(asked).clarification).toBe('waiting');
    const resumed = statuses([
      ...asked,
      ev('decision', 'completed', { tool: 'submit_l', status: 'ok' }),
    ]);
    expect(resumed.clarification).toBe('done');
    expect(resumed.decision).toBe('in_progress');
  });

  it('평가자 검토가 시작되면 판단을 끝내고, 최종 작성에서 검토를 끝낸다', () => {
    const reviewing = statuses([ev('evaluation', 'started')]);
    expect(reviewing.decision).toBe('done');
    expect(reviewing.evaluation).toBe('in_progress');
    const writing = statuses([
      ev('evaluation', 'started'),
      ev('evaluation', 'completed', { actor: 'founder', error_code: null }),
      ev('final', 'started', { feedback_round: 1 }),
    ]);
    expect(writing.evaluation).toBe('done');
    expect(writing.report).toBe('in_progress');
  });

  it('최종 완료면 질문이 없었어도 모든 단계를 완료로 표시한다', () => {
    const result = statuses([
      ev('address', 'started'),
      ev('final', 'completed', { review_completeness: 1 }),
    ]);
    expect(Object.values(result).every((status) => status === 'done')).toBe(
      true
    );
  });
});

describe('질문·답변 변환', () => {
  it('백엔드 질문을 직접 입력·모르겠어요·건너뛰기 카드로 바꾼다', () => {
    const [floor] = toClarifyingQuestions(waiting);
    expect(floor.questionId).toBe('floor');
    expect(floor.question).toBe('몇 층인가요?');
    expect(floor.reason).toBe('층에 따라 가능한 업종이 다릅니다.');
    expect(floor.options.map((option) => option.id)).toEqual([
      'answered',
      'unknown',
      'skipped',
    ]);
    expect(floor.options[0].detailInput?.required).toBe(true);
  });

  it('GET 질문 칸에 요청 ID를 붙여 대기 상태로 바꾼다', () => {
    expect(
      toWaiting('req-1', {
        question_session_id: 'qs-1',
        questions: waiting.questions,
        status: 'waiting',
      })
    ).toEqual(waiting);
  });

  it('층·전용면적 질문에만 앞에서 받은 값을 미리 채운다', () => {
    expect(
      prefillAnswers(waiting, { floor: ' 4층 401호 ', exclusiveArea: '85㎡' })
    ).toEqual({ floor: { optionId: ANSWERED_OPTION_ID, detail: '4층 401호' } });
  });

  it('모든 질문에 빈칸 없는 답을 넣고 고르지 않은 질문은 건너뛰기 문장으로 보낸다', () => {
    expect(
      toAnswerSubmission(waiting, {
        floor: { optionId: 'answered', detail: '1층' },
      })
    ).toEqual({
      request_id: 'req-1',
      question_session_id: 'qs-1',
      answers: { floor: '1층', space_condition: SKIPPED_ANSWER },
    });
    expect(
      toAnswerSubmission(waiting, {
        floor: { optionId: 'answered', detail: '  ' },
        space_condition: { optionId: 'unknown' },
      }).answers
    ).toEqual({ floor: SKIPPED_ANSWER, space_condition: UNKNOWN_ANSWER });
  });

  it('답은 백엔드 상한 500자로 자른다', () => {
    const long = '가'.repeat(600);
    expect(
      toAnswerSubmission(waiting, {
        floor: { optionId: 'answered', detail: long },
      }).answers.floor
    ).toHaveLength(500);
  });
});

describe('pollInterval', () => {
  it('처음 1초, 10초 뒤 2초, 1분 뒤 3초', () => {
    expect(pollInterval(0)).toBe(1_000);
    expect(pollInterval(10_000)).toBe(2_000);
    expect(pollInterval(60_000)).toBe(3_000);
  });
});
