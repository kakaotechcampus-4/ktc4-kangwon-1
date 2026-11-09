import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from './page';
import { login } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const query = vi.hoisted(() => ({ value: '' }));

vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ refresh: vi.fn() }),
}));
vi.mock('@/lib/api/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/auth')>()),
  login: vi.fn(),
}));

const RESET_DONE = '비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.';

async function submitLogin() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('이메일'), 'a@b.com');
  await user.type(screen.getByLabelText('비밀번호'), 'password1!');
  await user.click(screen.getByRole('button', { name: '로그인' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  query.value = '';
});

describe('로그인 화면', () => {
  it('재설정 뒤에는 완료 안내를 보여 준다', () => {
    query.value = 'reset=done';
    render(<LoginPage />);
    expect(screen.getByRole('status').textContent).toBe(RESET_DONE);
  });

  it('평소에는 안내가 없다', () => {
    render(<LoginPage />);
    expect(screen.queryByText(RESET_DONE)).toBeNull();
  });

  it('로그인에 실패하면 오류만 보인다', async () => {
    query.value = 'reset=done';
    vi.mocked(login).mockRejectedValue(
      new ApiError(401, '이메일 또는 비밀번호가 맞지 않습니다.')
    );
    render(<LoginPage />);
    await submitLogin();
    expect((await screen.findByRole('alert')).textContent).toBe(
      '이메일 또는 비밀번호가 맞지 않습니다.'
    );
    expect(screen.queryByText(RESET_DONE)).toBeNull();
  });

  it('next가 있으면 로그인 뒤 그리로 간다', async () => {
    query.value = 'reset=done&next=/my/reports';
    vi.mocked(login).mockResolvedValue(undefined as never);
    render(<LoginPage />);
    await submitLogin();
    await vi.waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/my/reports')
    );
  });
});
