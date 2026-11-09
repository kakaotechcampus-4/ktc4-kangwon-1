import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SignupPage from '@/app/signup/page';
import { signup } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';

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
const SERVER_TERMS_REQUIRED = '이용약관에 동의해야 가입할 수 있습니다.';
const KAKAO_NOTICE =
  '카카오로 시작하면 만 14세 이상이며 이용약관에 동의하고 개인정보 처리방침을 확인한 것으로 봅니다.';

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(signup).mockResolvedValue({ verification_sent: true });
  refresh.mockResolvedValue(undefined);
});

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function fillForm() {
  const user = userEvent.setup();
  render(<SignupPage />);
  fill('이메일', 'a');
  await user.selectOptions(
    screen.getByLabelText('이메일 도메인 선택'),
    '직접 입력'
  );
  fill('이메일 도메인 직접 입력', 'b.com');
  fill('비밀번호', '1234567890');
  fill('비밀번호 확인', '1234567890');
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

  it('동의하라는 오류 문구를 체크 칸 설명으로 이어 준다', async () => {
    const user = await fillForm();
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    const box = screen.getByRole('checkbox', { description: TERMS_REQUIRED });
    const message = document.getElementById(
      box.getAttribute('aria-describedby') ?? ''
    );
    expect(message?.getAttribute('role')).toBe('alert');
  });

  it('동의 안내를 받은 뒤 체크하면 오류 표시를 지운다', async () => {
    const user = await fillForm();
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    await user.click(screen.getByRole('checkbox'));
    expect(document.body.textContent).not.toContain(TERMS_REQUIRED);
    const box = screen.getByRole('checkbox');
    expect(box.getAttribute('aria-invalid')).toBeNull();
    expect(box.getAttribute('aria-describedby')).toBeNull();
  });

  it('서버가 약관 동의가 없다고 거절해도 체크 칸에 오류를 표시한다', async () => {
    vi.mocked(signup).mockRejectedValue(
      new ApiError(422, SERVER_TERMS_REQUIRED)
    );
    const user = await fillForm();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    const box = await screen.findByRole('checkbox', {
      description: SERVER_TERMS_REQUIRED,
    });
    expect(box.getAttribute('aria-invalid')).toBe('true');
  });

  it('약관과 상관없는 서버 거절은 체크 칸을 오류로 표시하지 않는다', async () => {
    vi.mocked(signup).mockRejectedValue(
      new ApiError(422, '너무 흔한 비밀번호입니다.')
    );
    const user = await fillForm();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: '가입하기' }));
    await screen.findByText('너무 흔한 비밀번호입니다.');
    const box = screen.getByRole('checkbox');
    expect(box.getAttribute('aria-invalid')).toBeNull();
    expect(box.getAttribute('aria-describedby')).toBeNull();
  });

  it('"(필수)"가 혼자 줄을 바꾸지 않게 "동의합니다 (필수)"를 묶는다', () => {
    render(<SignupPage />);
    expect(screen.getByText('동의합니다 (필수)').className).toContain(
      'whitespace-nowrap'
    );
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

  it('체크하지 않은 칸 테두리는 흰 바탕에서도 보이는 회색 토큰을 쓴다', () => {
    render(<SignupPage />);
    expect(
      (screen.getByRole('checkbox') as HTMLInputElement).style.borderColor
    ).toBe('rgb(107, 114, 128)');
  });

  it('이름 칸이 없다', () => {
    render(<SignupPage />);
    expect(screen.queryByLabelText('이름')).toBeNull();
  });

  it('카카오로 시작하기 아래에 동의로 보는 범위를 알린다', () => {
    render(<SignupPage />);
    expect(document.body.textContent).toContain(KAKAO_NOTICE);
  });

  it('카카오로 시작하기 버튼이 아래 안내를 설명으로 가리킨다', () => {
    render(<SignupPage />);
    expect(
      screen.getByRole('button', {
        name: '카카오로 시작하기',
        description: KAKAO_NOTICE,
      })
    ).toBeTruthy();
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
