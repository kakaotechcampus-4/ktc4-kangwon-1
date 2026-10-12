import { describe, expect, it } from 'vitest';
import {
  ANSWERED_OPTION_ID,
  applyProgressEvent,
  prefillAnswers,
  toAnswerSubmission,
  toClarifyingQuestions,
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
  question_set_id: 'qs-1',
  questions: [
    {
      field: 'floor',
      text: '몇 층인가요?',
      why_needed: '층에 따라 가능한 업종이 다릅니다.',
      expected_impact: '1층 전용 업종 판단에 씁니다.',
    },
    {
      field: 'space_condition',
      text: '공간 상태는 어떤가요?',
      why_needed: '공사 범위를 판단합니다.',
      expected_impact: '설비 공사가 큰 업종을 거릅니다.',
    },
  ],
};

describe('applyProgressEvent', () => {
  it('세 분석이 시작되면 자료 수집을 끝내고 각 분석을 진행 중으로 둔다', () => {
    const result = statuses([
      ev('address', 'started'),
      ev('floating_population', 'started'),
      ev('commercial_area', 'started'),
      ev('business_lifecycle', 'started'),
      ev('commercial_area', 'completed', { status: 'ok' }),
    ]);
    expect(result['data-collection']).toBe('done');
    expect(result['commercial-area']).toBe('done');
    expect(result['floating-population']).toBe('in_progress');
    expect(result['business-lifecycle']).toBe('in_progress');
  });

  it('질문 대기 → 답변 후 재판단 → 완료 순서를 반영한다', () => {
    const asked = [
      ev('decision', 'started'),
      ev('decision', 'completed', { action: 'ask_user' }),
      ev('questions', 'waiting', { count: 2 }),
    ];
    const waitingState = statuses(asked);
    expect(waitingState.clarification).toBe('waiting');
    expect(waitingState.decision).toBe('pending');

    const resumed = statuses([...asked, ev('decision', 'started')]);
    expect(resumed.clarification).toBe('done');
    expect(resumed.decision).toBe('in_progress');

    const finished = statuses([
      ...asked,
      ev('decision', 'started'),
      ev('decision', 'completed', { action: 'final' }),
    ]);
    expect(finished.decision).toBe('done');
  });

  it('질문 없이 끝나면 모든 단계를 완료로 표시한다', () => {
    const result = statuses([
      ev('decision', 'started'),
      ev('decision', 'completed', { action: 'final' }),
      ev('run', 'completed', { status: 'ok' }),
    ]);
    expect(Object.values(result).every((status) => status === 'done')).toBe(
      true
    );
  });

  it('보완·지도·전문가 작업은 최종 판단 진행 중으로 묶는다', () => {
    expect(statuses([ev('supplement', 'started')]).decision).toBe(
      'in_progress'
    );
    expect(statuses([ev('consult.commercial_area', 'started')]).decision).toBe(
      'in_progress'
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

  it('층·전용면적 질문에만 앞에서 받은 값을 미리 채운다', () => {
    expect(
      prefillAnswers(waiting, { floor: ' 4층 401호 ', exclusiveArea: '85㎡' })
    ).toEqual({ floor: { optionId: ANSWERED_OPTION_ID, detail: '4층 401호' } });
  });

  it('답변을 제출 형식으로 바꾸고 고르지 않은 질문은 건너뛰기로 보낸다', () => {
    expect(
      toAnswerSubmission(waiting, {
        floor: { optionId: 'answered', detail: '1층' },
      })
    ).toEqual({
      request_id: 'req-1',
      question_set_id: 'qs-1',
      answers: [
        { field: 'floor', status: 'answered', value: '1층' },
        { field: 'space_condition', status: 'skipped' },
      ],
    });
    expect(
      toAnswerSubmission(waiting, {
        floor: { optionId: 'answered', detail: '  ' },
        space_condition: { optionId: 'unknown' },
      }).answers
    ).toEqual([
      { field: 'floor', status: 'skipped' },
      { field: 'space_condition', status: 'unknown' },
    ]);
  });
});

describe('pollInterval', () => {
  it('처음 1초, 10초 뒤 2초, 1분 뒤 3초', () => {
    expect(pollInterval(0)).toBe(1_000);
    expect(pollInterval(10_000)).toBe(2_000);
    expect(pollInterval(60_000)).toBe(3_000);
  });
});
