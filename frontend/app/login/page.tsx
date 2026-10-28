'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import AuthShell from '@/components/auth/AuthShell';
import FormField from '@/components/auth/FormField';
import FormMessage from '@/components/auth/FormMessage';
import KakaoButton from '@/components/auth/KakaoButton';
import PasswordField from '@/components/auth/PasswordField';
import { useAuth } from '@/components/auth/AuthProvider';
import Button from '@/components/ui/Button';
import { KAKAO_ERRORS, login, safeNext } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';
import { colors } from '@/styles/tokens';

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const next = safeNext(params.get('next'));

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // 카카오 쪽 실패는 주소창의 ?error= 로 돌아온다.
  const [error, setError] = useState(
    () => KAKAO_ERRORS[params.get('error') ?? ''] ?? ''
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await login(email, password);
      await refresh();
      router.replace(next);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : '로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      );
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="로그인"
      description="공실 분석을 시작하려면 로그인해 주세요."
      footer={
        <>
          아직 계정이 없으신가요?{' '}
          <Link
            href={`/signup?next=${encodeURIComponent(next)}`}
            className="font-semibold underline underline-offset-2"
            style={{ color: colors.brand.dark }}
          >
            회원가입
          </Link>
        </>
      }
    >
      <KakaoButton next={next} />

      <div className="flex items-center gap-3">
        <span
          className="h-px flex-1"
          style={{ backgroundColor: colors.neutral.border }}
        />
        <span className="text-13" style={{ color: colors.text.tertiary }}>
          또는 이메일로
        </span>
        <span
          className="h-px flex-1"
          style={{ backgroundColor: colors.neutral.border }}
        />
      </div>

      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <FormField
          label="이메일"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <PasswordField
          label="비밀번호"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {error ? <FormMessage tone="error">{error}</FormMessage> : null}

        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? '로그인하는 중…' : '로그인'}
        </Button>
      </form>

      <Link
        href="/password/forgot"
        className="self-center text-15 underline underline-offset-2"
        style={{ color: colors.text.secondary }}
      >
        비밀번호를 잊으셨나요?
      </Link>
    </AuthShell>
  );
}
