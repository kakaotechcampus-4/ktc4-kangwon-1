'use client';

import { useEffect, type ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import VerificationNotice from '@/components/auth/VerificationNotice';
import { loginPath } from '@/lib/api/auth';
import { colors } from '@/styles/tokens';

/**
 * 화면 쪽 가드다. 실제 차단은 백엔드가 한다(401·403).
 * 쿠키가 백엔드 도메인에 있어 Next 서버는 읽지 못하므로 middleware로는 못 막는다.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === 'anonymous') {
      router.replace(loginPath(pathname, window.location.search));
    }
  }, [status, pathname, router]);

  // 서버 렌더링에서는 쿠키를 못 읽어 항상 loading으로 시작한다. 깜빡임을 막는다.
  if (status === 'loading' || status === 'anonymous') {
    return <AuthSkeleton />;
  }

  if (user?.needs_verification) {
    return <VerificationNotice email={user.email} />;
  }

  return <>{children}</>;
}

function AuthSkeleton() {
  return (
    <div
      className="flex flex-1 items-center justify-center py-24"
      role="status"
      aria-label="로그인 상태를 확인하는 중"
    >
      <div className="flex w-full max-w-md flex-col gap-3 px-8">
        {[72, 100, 56].map((width) => (
          <div
            key={width}
            className="h-4 animate-pulse rounded"
            style={{
              width: `${width}%`,
              backgroundColor: colors.neutral.border,
            }}
          />
        ))}
      </div>
    </div>
  );
}
