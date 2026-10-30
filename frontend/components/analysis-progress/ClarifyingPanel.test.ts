import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClarifyingAnswers } from '@/lib/mockData/analysisProgress';

const state = vi.hoisted(() => ({ answers: {} as ClarifyingAnswers }));

vi.mock('@/styles/fonts', () => ({
  pretendard: { className: 'test-font', variable: 'test-font-variable' },
}));

// 사용자 선택 이후 상태를 주입해 공통 UI의 표시·검증을 확인한다.
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    useState: (initial: unknown) =>
      actual.useState(
        typeof initial === 'object' && initial !== null
          ? state.answers
          : initial
      ),
  };
});

import ClarifyingPanel from './ClarifyingPanel';
import { demoClarifyingQuestions as questions } from '@/lib/mockData/clarifyingDemo';

function render(stage: 'awaiting_input' | 'resuming' = 'awaiting_input') {
  return renderToStaticMarkup(
    createElement(ClarifyingPanel, {
      stage,
      steps: [],
      questions,
      onSubmit: vi.fn(),
      onViewReport: vi.fn(),
    })
  );
}

function submitDisabled(html: string) {
  return /<button[^>]*disabled=""[^>]*>답변하고 분석 이어가기/.test(html);
}

beforeEach(() => {
  state.answers = {};
});

describe('새 질문 데이터에 따른 공통 UI', () => {
  it('새 질문의 4개·2개 선택지를 각 문구로 표시한다', () => {
    const html = render();
    for (const question of questions) {
      expect(html).toContain(question.question);
      for (const option of question.options)
        expect(html).toContain(option.label);
    }
    expect(submitDisabled(html)).toBe(true);
    expect(html).not.toContain('협의할 내용을 적어주세요');
  });

  it.each(['', '   '])(
    '새 필수 입력이 비어 있으면 제출을 막는다: %j',
    (detail) => {
      state.answers = {
        'new-ventilation-question': { optionId: 'approval', detail },
        'new-sign-question': { optionId: 'yes' },
      };
      const html = render();
      expect(html).toContain('협의할 내용을 적어주세요');
      expect(html).toContain('placeholder="예: 외벽 타공 허가 필요"');
      expect(html).toContain('required=""');
      expect(submitDisabled(html)).toBe(true);
    }
  );

  it('새 필수 입력을 작성하면 제출을 허용하고 선택 입력은 비워도 된다', () => {
    state.answers = {
      'new-ventilation-question': {
        optionId: 'approval',
        detail: '외벽 타공 허가 필요',
      },
      'new-sign-question': { optionId: 'conditional' },
    };
    const html = render();
    expect(html).toContain('간판 조건');
    expect(submitDisabled(html)).toBe(false);
  });

  it('다른 선택지에는 상세 입력을 표시하지 않고 이전 상세 내용도 요약에서 제외한다', () => {
    state.answers = {
      'new-ventilation-question': {
        optionId: 'ready',
        detail: '이전 협의 내용',
      },
      'new-sign-question': { optionId: 'yes' },
    };
    expect(render()).not.toContain('협의할 내용을 적어주세요');
    expect(submitDisabled(render())).toBe(false);
    const summary = render('resuming');
    expect(summary).toContain('설치되어 있어요');
    expect(summary).not.toContain('이전 협의 내용');
  });

  it('질문별 상세 내용을 분리해 요약에 표시한다', () => {
    state.answers = {
      'new-ventilation-question': {
        optionId: 'approval',
        detail: '외벽 타공 허가 필요',
      },
      'new-sign-question': { optionId: 'conditional', detail: '가로 2m 이하' },
    };
    const summary = render('resuming');
    expect(summary).toContain('건물주 협의가 필요해요: 외벽 타공 허가 필요');
    expect(summary).toContain('조건이 있어요: 가로 2m 이하');
  });

  it('질문에 없는 선택지 ID를 완료된 답변으로 처리하지 않는다', () => {
    state.answers = {
      'new-ventilation-question': { optionId: 'obsolete-option' },
      'new-sign-question': { optionId: 'yes' },
    };
    expect(submitDisabled(render())).toBe(true);
  });
});
