'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import AuthShell from '@/components/auth/AuthShell';
import FormMessage from '@/components/auth/FormMessage';
import PasswordField from '@/components/auth/PasswordField';
import { useAuth } from '@/components/auth/AuthProvider';
import Button from '@/components/ui/Button';
import { resetPassword } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';

const MIN_PASSWORD_LENGTH = 10;

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPassword />
    </Suspense>
  );
}

function ResetPassword() {
  const token = useSearchParams().get('token') ?? '';
  const router = useRouter();
  const { clear } = useAuth();
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await resetPassword(token, password);
      // 서버가 이 사용자의 모든 세션을 끊는다. 화면 상태도 같이 비운다.
      clear();
      router.replace('/login?reset=done');
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : '비밀번호를 바꾸지 못했습니다. 잠시 후 다시 시도해 주세요.'
      );
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthShell
        eyebrow="PASSWORD"
        title="링크가 올바르지 않습니다"
        description="메일에 담긴 링크를 다시 눌러 주세요."
        footer={
          <Link
            href="/password/forgot"
            className="underline underline-offset-2"
          >
            재설정 링크 다시 받기
          </Link>
        }
      >
        <span />
      </AuthShell>
    );
  }

  return (
    <AuthShell
      eyebrow="PASSWORD"
      title="새 비밀번호 설정"
      description="바꾸고 나면 다른 기기의 로그인도 모두 해제됩니다."
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <PasswordField
          label="새 비밀번호"
          name="new_password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          hint={`${MIN_PASSWORD_LENGTH}자 이상으로 정해 주세요.`}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error ? <FormMessage tone="error">{error}</FormMessage> : null}
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? '바꾸는 중…' : '비밀번호 바꾸기'}
        </Button>
      </form>
    </AuthShell>
  );
}
