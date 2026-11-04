import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReportPage from './page';
import { getAnalysis, getAnalysisFacts } from '@/lib/api/analyses';
import type {
  DecisionResult,
  FinalCandidate,
  StoredAnalysis,
} from '@/lib/api/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('next/script', () => ({ default: () => null }));
vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/components/auth/RequireAuth', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@/lib/api/analyses', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/analyses')>()),
  getAnalysis: vi.fn(),
  getAnalysisFacts: vi.fn(),
}));

const candidate: FinalCandidate = {
  industry_code: 'I21201',
  industry_name: '시험용 수제과자점',
  code_points: 62,
  L_points: 6,
  L_status: 'observed',
  A: 90,
  B: 60,
  H: 80,
  lower_ratio: 0.67,
  upper_ratio: 0.89,
  coverage: 0.8,
  demand_coverage: 0.8,
  competition_coverage: 0.8,
  G: '해당 없음',
  badge: '추천',
  confirmation_conditions: [],
  reasons_segments: [{ type: 'text', text: '주변 직장인이 많습니다.' }],
  risks_segments: [],
  confirmation_conditions_segments: [],
  fact_ids: [],
  review_state: 'reviewed',
};

const result = {
  schema_version: '2.0',
  rubric_version: 'v1',
  tool_contract_version: 'v1',
  request_id: 'r1',
  run_id: 'run-1',
  report_id: 'rep-1',
  snapshot_id: 'snap-1',
  score_snapshot_id: 'score-1',
  summary_segments: [{ type: 'text', text: '직장인 수요가 가장 큽니다.' }],
  top5: [candidate],
  excluded_candidates: [],
  facts: [],
  L_records: [],
  evaluator_reviews: [],
  review_completeness: 1,
  review_resolutions: [],
  confirmation_conditions_segments: [],
  limitations_segments: [],
} as DecisionResult;

const stored: StoredAnalysis = {
  request_id: 'r1',
  status: 'completed',
  site: {
    input_address: '서울 송파구 위례광장로 199 1층',
    road_address: '서울특별시 송파구 위례광장로 199',
    detail_address: '1층',
  },
  result,
  error: null,
  questions: null,
  rendered: null,
  input_address: '서울 송파구 위례광장로 199 1층',
  completed_at: '2026-11-03T03:00:00+00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, '', '/report?id=r1');
  vi.mocked(getAnalysisFacts).mockResolvedValue({
    request_id: 'r1',
    snapshot_id: null,
    facts: [],
  });
});

describe('리포트 화면', () => {
  it('서버에서 받은 추천 업종과 주소를 보여 준다', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(stored);
    render(<ReportPage />);
    await waitFor(() =>
      expect(document.body.textContent).toContain('직장인 수요가 가장 큽니다.')
    );
    expect(document.body.textContent).toContain('시험용 수제과자점');
    expect(document.body.textContent).toContain('위례광장로 199');
    expect(getAnalysis).toHaveBeenCalledWith('r1');
  });

  it('PDF 다운로드를 누르면 예쁜 이름으로 인쇄 창을 연다', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(stored);
    const titles: string[] = [];
    vi.spyOn(window, 'print').mockImplementation(() =>
      titles.push(document.title)
    );
    render(<ReportPage />);
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: 'PDF 다운로드' }));
    expect(titles).toEqual([
      '채움 업종분석 리포트 - 서울특별시 송파구 위례광장로 199 1층 (2026.11.03)',
    ]);
  });

  it('불러오지 못하면 안내와 다시 불러오기를 보여 준다', async () => {
    vi.mocked(getAnalysis)
      .mockRejectedValueOnce(new Error('리포트를 불러오지 못했어요.'))
      .mockResolvedValue(stored);
    render(<ReportPage />);
    expect(await screen.findByText('리포트를 불러오지 못했어요.')).toBeTruthy();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /다시 불러오기/ }));
    await waitFor(() => expect(getAnalysis).toHaveBeenCalledTimes(2));
  });

  it('예시 보기로 열면 예시 리포트라고 표시한다', async () => {
    window.history.replaceState({}, '', '/report?example=1');
    render(<ReportPage />);
    expect(
      await screen.findByText(
        /예시 리포트예요\. 실제 상가를 분석한 결과가 아니에요\./
      )
    ).toBeTruthy();
    expect(getAnalysis).not.toHaveBeenCalled();
  });
});
