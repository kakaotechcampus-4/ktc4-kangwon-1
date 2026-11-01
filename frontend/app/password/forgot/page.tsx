'use client';

import { useState } from 'react';
import Link from 'next/link';
import AuthShell from '@/components/auth/AuthShell';
import FormField from '@/components/auth/FormField';
import FormMessage from '@/components/auth/FormMessage';
import Button from '@/components/ui/Button';
import { forgotPassword } from '@/lib/api/auth';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await forgotPassword(email);
    } catch {
      // 서버는 계정 유무와 무관하게 성공을 돌려준다. 실패해도 같은 안내를 보여
      // 가입 여부가 드러나지 않게 한다.
    }
    setSent(true);
    setSubmitting(false);
  }

  if (sent) {
    return (
      <AuthShell
        eyebrow="PASSWORD"
        title="메일을 보냈습니다"
        description="가입된 주소라면 비밀번호 재설정 링크가 도착합니다. 메일이 보이지 않으면 스팸함도 확인해 주세요."
        footer={
          <Link href="/login" className="underline underline-offset-2">
            로그인 화면으로
          </Link>
        }
      >
        <FormMessage tone="success">{email} 로 보냈습니다.</FormMessage>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      eyebrow="PASSWORD"
      title="비밀번호 찾기"
      description="가입한 이메일 주소를 입력하면 재설정 링크를 보내 드립니다."
      footer={
        <Link href="/login" className="underline underline-offset-2">
          로그인 화면으로
        </Link>
      }
    >
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
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? '보내는 중…' : '재설정 링크 받기'}
        </Button>
      </form>
    </AuthShell>
  );
}
