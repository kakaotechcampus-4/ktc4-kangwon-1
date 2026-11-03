import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AnalysisProgressPage from './page';
import type { DecisionResult, WaitingForInput } from '@/lib/api/types';
import { useAnalysisProgress } from '@/lib/hooks/useAnalysisProgress';
import { mockAnalysisProgress } from '@/lib/mockData/analysisProgress';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/lib/hooks/useAnalysisProgress', () => ({
  useAnalysisProgress: vi.fn(),
}));

type Progress = ReturnType<typeof useAnalysisProgress>;

const waiting: WaitingForInput = {
  status: 'waiting_for_input',
  request_id: 'r1',
  question_session_id: 'qs-1',
  questions: [
    {
      field: 'space_condition',
      question: '공간 상태는 어떤가요?',
      reason: '공사 범위를 판단합니다.',
    },
  ],
};

function progress(overrides: Partial<Progress>) {
  vi.mocked(useAnalysisProgress).mockReturnValue({
    steps: mockAnalysisProgress.steps,
    stage: 'analyzing',
    waiting: null,
    result: null,
    error: null,
    submitError: null,
    submit: vi.fn(),
    detail: null,
    ...overrides,
  } as Progress);
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, '', '/analysis-progress?id=r1');
});

describe('분석 진행 화면', () => {
  it('분석 번호 없이 열면 시작하기와 내 분석 기록을 안내한다', async () => {
    window.history.replaceState({}, '', '/analysis-progress');
    render(<AnalysisProgressPage />);
    expect(
      await screen.findByText('진행 중인 분석을 찾지 못했어요')
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: '공실 분석 시작하기' })
    ).toBeTruthy();
    expect(screen.getByRole('link', { name: '내 분석 기록' })).toBeTruthy();
    expect(useAnalysisProgress).not.toHaveBeenCalled();
  });

  it('답변을 기다리면 질문과 답변 버튼을 보여 준다', async () => {
    progress({ stage: 'awaiting_input', waiting });
    render(<AnalysisProgressPage />);
    expect(await screen.findByText('공간 상태는 어떤가요?')).toBeTruthy();
    expect(screen.getByRole('button', { name: /답변하고/ })).toBeTruthy();
  });

  it('실패하면 서버가 준 원인 안내를 그대로 보여 준다', async () => {
    const message = 'AI 분석이 끝나지 못했어요. 잠시 후 다시 분석해 주세요.';
    progress({ stage: 'failed', error: message });
    render(<AnalysisProgressPage />);
    expect(await screen.findByText(message)).toBeTruthy();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '다시 분석하기' }));
    expect(router.replace).toHaveBeenCalledWith('/vacancy-input');
  });

  it('끝나면 이 분석 번호의 리포트를 연다', async () => {
    progress({
      stage: 'completed',
      result: { request_id: 'r1' } as DecisionResult,
    });
    render(<AnalysisProgressPage />);
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: /리포트 보기/ }));
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/report?id=r1')
    );
  });
});
