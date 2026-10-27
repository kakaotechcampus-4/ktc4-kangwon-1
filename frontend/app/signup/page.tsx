'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import AuthShell from '@/components/auth/AuthShell';
import FormField from '@/components/auth/FormField';
import FormMessage from '@/components/auth/FormMessage';
import KakaoButton from '@/components/auth/KakaoButton';
import { useAuth } from '@/components/auth/AuthProvider';
import Button from '@/components/ui/Button';
import { safeNext, signup } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/http';
import { colors } from '@/styles/tokens';

const MIN_PASSWORD_LENGTH = 10;

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const next = safeNext(params.get('next'));

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
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
      await signup({ email, password, displayName: displayName.trim() });
      await refresh();
      // 가입 직후 바로 로그인된다. 메일 확인은 분석을 시작할 때 요구한다.
      router.replace(next);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : '가입하지 못했습니다. 잠시 후 다시 시도해 주세요.'
      );
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="회원가입"
      description="분석한 리포트를 계정에 저장해 다시 열어볼 수 있습니다."
      footer={
        <>
          이미 계정이 있으신가요?{' '}
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="font-semibold underline underline-offset-2"
            style={{ color: colors.brand.dark }}
          >
            로그인
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
        <FormField
          label="비밀번호"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          hint={`${MIN_PASSWORD_LENGTH}자 이상으로 정해 주세요.`}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <FormField
          label="이름"
          name="display_name"
          autoComplete="name"
          placeholder="리포트에 표시할 이름 (선택)"
          maxLength={50}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />

        {error ? <FormMessage tone="error">{error}</FormMessage> : null}

        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? '가입하는 중…' : '가입하기'}
        </Button>
      </form>
    </AuthShell>
  );
}
