'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import AuthShell from '@/components/auth/AuthShell';
import EmailField from '@/components/auth/EmailField';
import FormMessage from '@/components/auth/FormMessage';
import KakaoButton from '@/components/auth/KakaoButton';
import LegalLink from '@/components/auth/LegalLink';
import PasswordField from '@/components/auth/PasswordField';
import { useAuth } from '@/components/auth/AuthProvider';
import Button from '@/components/ui/Button';
import Checkbox from '@/components/ui/Checkbox';
import { safeNext, signup } from '@/lib/api/auth';
import { EMAIL_DOMAINS, isEmailLike, joinEmail } from '@/lib/api/email';
import { ApiError } from '@/lib/api/http';
import { colors } from '@/styles/tokens';

const MIN_PASSWORD_LENGTH = 10;
const TERMS_REQUIRED = '이용약관에 동의해 주세요.';
const SERVER_TERMS_REQUIRED = '이용약관에 동의해야 가입할 수 있습니다.';
const ERROR_ID = 'signup-error';

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

  const [local, setLocal] = useState('');
  const [domain, setDomain] = useState<string>(EMAIL_DOMAINS[0]);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [termsMissing, setTermsMissing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  // 이미 가입된 주소는 이메일 칸 바로 아래에서 알려줘야 눈이 덜 헤맨다.
  const [takenEmail, setTakenEmail] = useState('');

  const email = joinEmail(local, domain);
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  const mismatch = confirm.length > 0 && password !== confirm;
  const matched = confirm.length > 0 && password === confirm;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setTakenEmail('');
    setTermsMissing(false);

    if (!isEmailLike(email)) {
      setError('이메일 주소를 확인해 주세요.');
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`);
      return;
    }
    if (password !== confirm) {
      setError('비밀번호가 서로 다릅니다.');
      return;
    }
    if (!agreeTerms) {
      setTermsMissing(true);
      setError(TERMS_REQUIRED);
      return;
    }

    setSubmitting(true);
    try {
      await signup({ email, password, agreeTerms });
      await refresh();
      // 가입 직후 바로 로그인된다. 메일 확인은 분석을 시작할 때 요구한다.
      router.replace(next);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setTakenEmail(email);
      } else {
        setTermsMissing(
          caught instanceof ApiError &&
            caught.status === 422 &&
            caught.message === SERVER_TERMS_REQUIRED
        );
        setError(
          caught instanceof ApiError
            ? caught.message
            : '가입하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        );
      }
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="SIGN UP"
      title="회원가입"
      description="분석한 리포트를 계정에 저장해 다시 열어볼 수 있습니다."
      footer={
        <>
          이미 계정이 있으신가요?{' '}
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="underline underline-offset-2"
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
        <div className="flex flex-col gap-1.5">
          <EmailField
            local={local}
            domain={domain}
            onLocalChange={(value) => {
              setLocal(value);
              setTakenEmail('');
            }}
            onDomainChange={(value) => {
              setDomain(value);
              setTakenEmail('');
            }}
          />
          {takenEmail ? (
            <p
              role="alert"
              className="text-15 font-medium"
              style={{ color: colors.status.notRecommend }}
            >
              이미 가입된 이메일입니다 ·{' '}
              <Link
                href={`/login?next=${encodeURIComponent(next)}`}
                className="font-bold underline underline-offset-2"
                style={{ color: colors.brand.primary }}
              >
                로그인하기
              </Link>
            </p>
          ) : null}
        </div>

        <PasswordField
          label="비밀번호"
          name="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          hint={`${MIN_PASSWORD_LENGTH}자 이상으로 정해 주세요.`}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          status={
            tooShort ? (
              <p
                className="text-13"
                style={{ color: colors.status.notRecommend }}
              >
                {MIN_PASSWORD_LENGTH - password.length}자 더 필요합니다.
              </p>
            ) : null
          }
        />

        <PasswordField
          label="비밀번호 확인"
          name="password_confirm"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          status={
            mismatch ? (
              <p
                className="text-13"
                style={{ color: colors.status.notRecommend }}
              >
                비밀번호가 서로 다릅니다.
              </p>
            ) : matched ? (
              <p className="text-13" style={{ color: colors.brand.primary }}>
                일치합니다.
              </p>
            ) : null
          }
        />

        <div className="flex flex-col gap-2">
          <Checkbox
            id="agree-terms"
            checked={agreeTerms}
            invalid={termsMissing}
            describedBy={termsMissing ? ERROR_ID : undefined}
            onChange={(value) => {
              setAgreeTerms(value);
              if (termsMissing) {
                setTermsMissing(false);
                setError('');
              }
            }}
          >
            만 14세 이상이며 <LegalLink href="/terms">이용약관</LegalLink>에{' '}
            <span className="whitespace-nowrap">동의합니다 (필수)</span>
          </Checkbox>
          <p className="text-13 break-keep text-[#4B5866]">
            개인정보는 <LegalLink href="/privacy">개인정보 처리방침</LegalLink>
            에 따라 처리됩니다.
          </p>
        </div>

        {error ? (
          <FormMessage tone="error" id={ERROR_ID}>
            {error}
          </FormMessage>
        ) : null}

        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? '가입하는 중…' : '가입하기'}
        </Button>
      </form>
    </AuthShell>
  );
}
