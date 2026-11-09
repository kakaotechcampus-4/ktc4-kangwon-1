import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HeaderUserMenu from '@/components/layout/HeaderUserMenu';
import { useAuth } from '@/components/auth/AuthProvider';
import { logout } from '@/lib/api/auth';

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/',
}));
vi.mock('@/components/auth/AuthProvider', () => ({ useAuth: vi.fn() }));
vi.mock('@/lib/api/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/auth')>()),
  logout: vi.fn(),
}));

const clear = vi.fn();

function signedIn(displayName: string) {
  vi.mocked(useAuth).mockReturnValue({
    status: 'authenticated',
    user: { display_name: displayName, email: 'a@b.com' },
    clear,
  } as unknown as ReturnType<typeof useAuth>);
}

describe('HeaderUserMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signedIn('김채움');
  });

  it('로그인 후에는 계정 버튼이 메뉴를 열고 닫는다', async () => {
    const user = userEvent.setup();
    render(<HeaderUserMenu />);
    const button = screen.getByRole('button', { name: '내 계정 메뉴' });

    await user.click(button);
    expect(screen.getByRole('menu')).toBeTruthy();
    expect(
      screen.getAllByRole('menuitem').map((item) => item.textContent)
    ).toEqual(['내 분석 기록', '로그아웃']);

    await user.click(button);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('Esc로 닫히고 버튼에 초점이 돌아온다', async () => {
    const user = userEvent.setup();
    render(<HeaderUserMenu />);
    const button = screen.getByRole('button', { name: '내 계정 메뉴' });

    await user.click(button);
    screen.getByRole('menuitem', { name: '내 분석 기록' }).focus();
    expect(document.activeElement).not.toBe(button);
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it('메뉴 밖을 누르면 닫힌다', async () => {
    const user = userEvent.setup();
    render(<HeaderUserMenu />);

    await user.click(screen.getByRole('button', { name: '내 계정 메뉴' }));
    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('이름이 이모지로 시작해도 첫 글자가 깨지지 않는다', () => {
    signedIn('🐻곰돌이');
    render(<HeaderUserMenu />);

    expect(
      screen.getByRole('button', { name: '내 계정 메뉴' }).textContent
    ).toContain('🐻');
  });

  it('로그아웃을 누르면 logout이 불리고 홈으로 간다', async () => {
    const user = userEvent.setup();
    vi.mocked(logout).mockResolvedValue(undefined);
    render(<HeaderUserMenu />);

    await user.click(screen.getByRole('button', { name: '내 계정 메뉴' }));
    await user.click(screen.getByRole('menuitem', { name: '로그아웃' }));

    expect(logout).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith('/');
  });

  it('로그인 전에는 로그인 링크가 보인다', () => {
    vi.mocked(useAuth).mockReturnValue({
      status: 'anonymous',
      user: null,
      clear,
    } as unknown as ReturnType<typeof useAuth>);
    render(<HeaderUserMenu />);

    expect(screen.getByRole('link', { name: '로그인' })).toBeTruthy();
  });

  it('이름 글자는 좁은 화면에서 숨긴다', () => {
    signedIn('아주아주아주아주 긴 이름의 사용자');
    render(<HeaderUserMenu />);

    const name = screen.getByText('아주아주아주아주 긴 이름의 사용자');
    expect(name.classList.contains('hidden')).toBe(true);
    expect(name.classList.contains('sm:inline')).toBe(true);
  });

  it('확인 중에는 좁은 화면에서 로그인 링크 폭만큼 자리를 비워 둔다', () => {
    vi.mocked(useAuth).mockReturnValue({
      status: 'loading',
      user: null,
      clear,
    } as unknown as ReturnType<typeof useAuth>);
    const { container } = render(<HeaderUserMenu />);

    const placeholder = container.firstChild as HTMLElement;
    expect(placeholder.classList.contains('w-[63px]')).toBe(true);
    expect(placeholder.classList.contains('sm:w-[86px]')).toBe(true);
  });
});
