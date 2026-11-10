import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MyReportsPage from '@/app/my/reports/page';
import { getMyAnalyses, withdraw } from '@/lib/api/auth';
import { WITHDRAWAL_EFFECT } from '@/lib/legal/terms';
import { openFresh } from '@/lib/navigation';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/components/auth/RequireAuth', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@/lib/navigation', () => ({ openFresh: vi.fn() }));
vi.mock('@/lib/api/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/auth')>();
  return { ...actual, getMyAnalyses: vi.fn(), withdraw: vi.fn() };
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getMyAnalyses).mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  });
});

async function typeConfirm() {
  const user = userEvent.setup();
  await user.type(
    await screen.findByLabelText('확인을 위해 "탈퇴"라고 입력해 주세요'),
    '탈퇴'
  );
  return user;
}

describe('내 분석 기록 화면의 탈퇴', () => {
  it('지워지는 것과 남는 것을 약관 문장 그대로 알린다', async () => {
    render(<MyReportsPage />);
    expect(await screen.findByText(WITHDRAWAL_EFFECT)).toBeTruthy();
  });

  it('질문 답 글까지 지우려면 버튼 대신 메일로 요청하라고 알린다', async () => {
    render(<MyReportsPage />);
    expect(
      await screen.findByText(
        /질문 답 글까지 지우려면 탈퇴 버튼을 누르지 말고 chaeum\.ai@gmail\.com으로 요청해 주세요\. 답 글을 지운 뒤 탈퇴까지 함께 처리합니다\./
      )
    ).toBeTruthy();
  });

  it('"탈퇴"를 입력하기 전에는 탈퇴 버튼이 꺼져 있다', async () => {
    render(<MyReportsPage />);
    const button = await screen.findByRole('button', { name: '탈퇴하기' });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    await typeConfirm();
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });

  it('탈퇴하면 첫 화면을 새로 열어 로그인 상태를 처음부터 다시 읽는다', async () => {
    vi.mocked(withdraw).mockResolvedValue();
    sessionStorage.setItem('chaeum:vacancyInput', 'x');
    sessionStorage.setItem('chaeum:confirmedBuilding', 'x');
    render(<MyReportsPage />);
    const user = await typeConfirm();
    await user.click(screen.getByRole('button', { name: '탈퇴하기' }));
    expect(withdraw).toHaveBeenCalledTimes(1);
    expect(openFresh).toHaveBeenCalledWith('/?withdrawn=1');
    expect(router.push).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('chaeum:vacancyInput')).toBeNull();
    expect(sessionStorage.getItem('chaeum:confirmedBuilding')).toBeNull();
  });

  it('탈퇴가 실패하면 서버 문장을 보여 주고 이 화면에 머문다', async () => {
    vi.mocked(withdraw).mockRejectedValue(
      new Error('잠시 후 다시 시도해 주세요.')
    );
    render(<MyReportsPage />);
    const user = await typeConfirm();
    await user.click(screen.getByRole('button', { name: '탈퇴하기' }));
    expect(await screen.findByText('잠시 후 다시 시도해 주세요.')).toBeTruthy();
    expect(openFresh).not.toHaveBeenCalled();
  });
});
