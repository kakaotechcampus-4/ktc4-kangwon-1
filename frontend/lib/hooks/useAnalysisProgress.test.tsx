import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAnalysisProgress } from '@/lib/hooks/useAnalysisProgress';
import { mockAnalysisProgress } from '@/lib/mockData/analysisProgress';
import { AnalysisApiError, getAnalysisEvents } from '@/lib/api/analyses';
import type { AnalysisEvents } from '@/lib/api/types';

vi.mock('@/lib/api/analyses', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/analyses')>();
  return {
    ...actual,
    getAnalysis: vi.fn(),
    getAnalysisEvents: vi.fn(),
    submitAnswers: vi.fn(),
  };
});

const running: AnalysisEvents = {
  request_id: 'r1',
  status: 'running',
  events: [],
  finished: false,
  next_after: 0,
};

async function pollTimes(count: number) {
  for (let i = 0; i < count; i += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getAnalysisEvents).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useAnalysisProgress 연결 끊김', () => {
  it('연결이 계속 끊겨도 실패로 바꾸지 않고 같은 분석에 다시 붙는다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new TypeError('Failed to fetch')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    expect(result.current.stage).toBe('analyzing');
    expect(result.current.disconnected).toBe(true);
    expect(result.current.error).toBeNull();

    vi.mocked(getAnalysisEvents).mockResolvedValue(running);
    await pollTimes(2);
    expect(result.current.disconnected).toBe(false);
    expect(
      vi.mocked(getAnalysisEvents).mock.calls.every(([id]) => id === 'r1')
    ).toBe(true);
  });

  it('서버가 5xx를 돌려줘도 연결 끊김으로 보고 기다린다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new AnalysisApiError(503, '잠시 후 다시 시도해 주세요.')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    expect(result.current.stage).toBe('analyzing');
    expect(result.current.disconnected).toBe(true);
  });

  it('분석을 찾을 수 없는 오류는 지금처럼 실패로 알린다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new AnalysisApiError(404, '분석을 찾을 수 없습니다.')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    expect(result.current.stage).toBe('failed');
    expect(result.current.error).toBe('분석을 찾을 수 없습니다.');
  });

  it('끊긴 뒤 다른 오류로 실패하면 끊김 표시를 지운다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new AnalysisApiError(503, '잠시 후 다시 시도해 주세요.')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    expect(result.current.disconnected).toBe(true);

    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new AnalysisApiError(404, '분석을 찾을 수 없습니다.')
    );
    await pollTimes(8);
    expect(result.current.stage).toBe('failed');
    expect(result.current.disconnected).toBe(false);
  });

  it('다시 연결해도 조회가 두 겹으로 돌지 않는다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new TypeError('Failed to fetch')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    vi.mocked(getAnalysisEvents).mockResolvedValue(running);
    await act(async () => {
      result.current.reconnect();
      await vi.advanceTimersByTimeAsync(0);
    });
    const start = vi.mocked(getAnalysisEvents).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(
      vi.mocked(getAnalysisEvents).mock.calls.length - start
    ).toBeLessThanOrEqual(5);
  });

  it('지금 다시 연결을 누르면 바로 다시 조회한다', async () => {
    vi.mocked(getAnalysisEvents).mockRejectedValue(
      new TypeError('Failed to fetch')
    );
    const { result } = renderHook(() =>
      useAnalysisProgress('r1', mockAnalysisProgress.steps)
    );
    await pollTimes(8);
    const before = vi.mocked(getAnalysisEvents).mock.calls.length;
    vi.mocked(getAnalysisEvents).mockResolvedValue(running);
    await act(async () => {
      result.current.reconnect();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.mocked(getAnalysisEvents).mock.calls.length).toBeGreaterThan(
      before
    );
    expect(result.current.disconnected).toBe(false);
  });
});
