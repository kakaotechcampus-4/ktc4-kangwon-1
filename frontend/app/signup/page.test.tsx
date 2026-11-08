import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SignupPage from '@/app/signup/page';
import { signup } from '@/lib/api/auth';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const refresh = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ refresh }),
}));
vi.mock('@/lib/api/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/auth')>()),
  signup: vi.fn(),
}));

const TERMS_REQUIRED = '이용약관에 동의해 주세요.';

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(signup).mockResolvedValue({ verification_sent: true });
  refresh.mockResolvedValue(undefined);
});

async function fillForm() {
  const user = userEvent.setup();
  render(<SignupPage />);
  await user.type(screen.getByLabelText('이메일'), 'a');
  await user.selectOptions(
    screen.getByLabelText('이메일 도메인 선택'),
    '직접 입력'
  );
  await user.type(screen.getByLabelText('이메일 도메인 직접 입력'), 'b.com');
  await user.type(screen.getByLabelText('비밀번호'), '1234567890');
  await user.type(screen.getByLabelText('비밀번호 확인'), '1234567890');
  return user;
}

describe('회원가입 화면', () => {
  it('약관에 동의하지 않으면 가입 요청을 보내지 않는다', async () => {
    const user = await fillForm();
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    expect(signup).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain(TERMS_REQUIRED);
    expect(screen.getByRole('checkbox').getAttribute('aria-invalid')).toBe(
      'true'
    );
  });

  it('동의하면 agreeTerms를 함께 보낸다', async () => {
    const user = await fillForm();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/'));
    expect(signup).toHaveBeenCalledWith({
      email: 'a@b.com',
      password: '1234567890',
      agreeTerms: true,
    });
  });

  it('동의 안내를 받은 뒤 체크하면 오류 표시를 지운다', async () => {
    const user = await fillForm();
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    await user.click(screen.getByRole('checkbox'));
    expect(document.body.textContent).not.toContain(TERMS_REQUIRED);
    expect(
      screen.getByRole('checkbox').getAttribute('aria-invalid')
    ).toBeNull();
  });

  it('체크박스 문구로 약관 동의 칸을 찾을 수 있다', () => {
    render(<SignupPage />);
    expect(
      screen.getByRole('checkbox', {
        name: '만 14세 이상이며 이용약관에 동의합니다 (필수)',
      })
    ).toBeTruthy();
    expect(document.body.textContent).toContain(
      '개인정보는 개인정보 처리방침에 따라 처리됩니다.'
    );
  });

  it('이름 칸이 없다', () => {
    render(<SignupPage />);
    expect(screen.queryByLabelText('이름')).toBeNull();
  });

  it('카카오로 시작하기 아래에 동의로 보는 범위를 알린다', () => {
    render(<SignupPage />);
    expect(document.body.textContent).toContain(
      '카카오로 시작하면 만 14세 이상이며 이용약관에 동의하고 개인정보 처리방침을 확인한 것으로 봅니다.'
    );
  });

  it('약관 링크는 새 탭으로 연다', () => {
    render(<SignupPage />);
    for (const [name, href] of [
      ['이용약관', '/terms'],
      ['개인정보 처리방침', '/privacy'],
    ]) {
      const links = screen.getAllByRole('link', { name });
      expect(links).toHaveLength(2);
      for (const link of links) {
        expect(link.getAttribute('href')).toBe(href);
        expect(link.getAttribute('target')).toBe('_blank');
        expect(link.getAttribute('rel')).toBe('noopener noreferrer');
      }
    }
  });
});
