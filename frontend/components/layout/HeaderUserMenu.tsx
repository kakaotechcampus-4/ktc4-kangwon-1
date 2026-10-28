'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { logout } from '@/lib/api/auth';
import { clearAnalysisResult, clearRequestId } from '@/lib/api/resultStore';
import { colors } from '@/styles/tokens';

export default function HeaderUserMenu() {
  const { status, user, clear } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function close(event: MouseEvent) {
      if (!wrapper.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  // 로그인 여부를 확인하는 동안 자리를 비워 둔다. 버튼이 깜빡이며 바뀌지 않게.
  if (status === 'loading') {
    return <div className="justify-self-end" style={{ width: 84 }} />;
  }

  if (status === 'anonymous') {
    return (
      <Link
        href={`/login?next=${encodeURIComponent(pathname)}`}
        className="justify-self-end rounded-lg px-4 py-2 text-15 font-semibold transition-opacity hover:opacity-80"
        style={{ color: colors.brand.dark }}
      >
        로그인
      </Link>
    );
  }

  const name = user?.display_name ?? user?.email ?? '내 계정';

  async function handleLogout() {
    try {
      await logout();
    } finally {
      // 서버 응답과 무관하게 이 브라우저에 남은 분석 흔적을 지운다.
      clearAnalysisResult();
      clearRequestId();
      clear();
      setOpen(false);
      router.push('/');
    }
  }

  return (
    <div ref={wrapper} className="relative justify-self-end">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex max-w-[180px] items-center gap-2 rounded-lg px-3 py-2 text-15 transition-colors hover:bg-gray-50"
        style={{ color: colors.text.primary }}
      >
        <span
          className="flex size-7 shrink-0 items-center justify-center rounded-full text-13 font-semibold"
          style={{
            backgroundColor: colors.brand.dark,
            color: colors.neutral.white,
          }}
        >
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="truncate">{name}</span>
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-20 flex w-44 flex-col overflow-hidden rounded-lg border shadow-[0px_4px_16px_0px_rgba(0,0,0,0.08)]"
          style={{
            backgroundColor: colors.neutral.white,
            borderColor: colors.neutral.border,
          }}
        >
          <Link
            href="/my/reports"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="px-4 py-3 text-left text-15 transition-colors hover:bg-gray-50"
            style={{ color: colors.text.primary }}
          >
            내 분석 기록
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="border-t px-4 py-3 text-left text-15 transition-colors hover:bg-gray-50"
            style={{
              color: colors.text.secondary,
              borderColor: colors.neutral.border,
            }}
          >
            로그아웃
          </button>
        </div>
      ) : null}
    </div>
  );
}
