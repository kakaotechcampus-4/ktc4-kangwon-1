'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import AuthShell from '@/components/auth/AuthShell';
import FormMessage from '@/components/auth/FormMessage';
import { useAuth } from '@/components/auth/AuthProvider';
import Button from '@/components/ui/Button';
import { verifyEmail } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmail />
    </Suspense>
  );
}

function VerifyEmail() {
  const token = useSearchParams().get('token') ?? '';
  const { refresh } = useAuth();
  // 토큰이 없다는 건 첫 렌더에 이미 아는 사실이라 그 상태로 시작한다.
  const [state, setState] = useState<'working' | 'done' | 'failed'>(
    token ? 'working' : 'failed'
  );
  const [message, setMessage] = useState(
    token ? '' : '확인 링크가 올바르지 않습니다.'
  );
  // 개발 중 이펙트가 두 번 도는 환경에서 토큰을 두 번 소비하지 않게 막는다.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) {
      return;
    }
    started.current = true;

    // 토큰은 주소가 아니라 본문으로 보낸다. 서버 접근 로그에 남지 않게.
    verifyEmail(token)
      .then(refresh)
      .then(() => setState('done'))
      .catch((caught: unknown) => {
        setState('failed');
        setMessage(
          caught instanceof ApiError
            ? caught.message
            : '확인하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        );
      });
  }, [token, refresh]);

  if (state === 'working') {
    return (
      <AuthShell
        title="이메일을 확인하는 중입니다"
        description="잠시만 기다려 주세요."
      >
        <span />
      </AuthShell>
    );
  }

  if (state === 'done') {
    return (
      <AuthShell
        title="확인이 끝났습니다"
        description="이제 공실 분석을 시작할 수 있습니다."
      >
        <Link href="/vacancy-input">
          <Button type="button" variant="primary" className="w-full">
            공실 분석 시작하기
          </Button>
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="확인하지 못했습니다"
      description="링크가 만료되었거나 이미 사용되었을 수 있습니다."
      footer={
        <Link href="/login" className="underline underline-offset-2">
          로그인 화면으로
        </Link>
      }
    >
      <FormMessage tone="error">{message}</FormMessage>
      <p className="text-15">로그인하면 인증 메일을 다시 보낼 수 있습니다.</p>
    </AuthShell>
  );
}
