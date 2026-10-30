'use client';

import { useState } from 'react';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import { resendVerification } from '@/lib/api/auth';
import { colors } from '@/styles/tokens';

/**
 * 이메일로 가입했지만 아직 메일 확인을 안 끝낸 사람이 보는 화면.
 * 로그인은 돼 있으므로 "다시 보내기"를 여기서 누를 수 있다.
 */
export default function VerificationNotice({
  email,
}: {
  email: string | null;
}) {
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>(
    'idle'
  );

  async function handleResend() {
    setState('sending');
    try {
      const { verification_sent } = await resendVerification();
      setState(verification_sent ? 'sent' : 'failed');
    } catch {
      setState('failed');
    }
  }

  return (
    <main className="flex flex-1 justify-center px-4 pt-16 pb-24">
      <Card className="w-full max-w-[480px] gap-5">
        <p
          className="text-sm font-bold tracking-[0.08em]"
          style={{ color: colors.brand.primary }}
        >
          EMAIL VERIFICATION
        </p>
        <h1
          className="text-3xl font-extrabold tracking-[-0.03em] break-keep"
          style={{ color: colors.brand.dark }}
        >
          이메일 확인을 끝내 주세요
        </h1>
        <p className="text-base break-keep text-[#4B5866]">
          {email ? (
            <>
              <b style={{ color: colors.text.primary }}>{email}</b> 으로 보낸
              메일의 버튼을 누르면 공실 분석을 시작할 수 있습니다.
            </>
          ) : (
            '가입할 때 보낸 메일의 버튼을 누르면 공실 분석을 시작할 수 있습니다.'
          )}
        </p>
        <p className="text-13" style={{ color: colors.text.tertiary }}>
          메일이 보이지 않으면 스팸함도 확인해 주세요.
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            onClick={handleResend}
            disabled={state === 'sending'}
          >
            {state === 'sending' ? '보내는 중…' : '인증 메일 다시 보내기'}
          </Button>
          {state === 'sent' ? (
            <span className="text-15" style={{ color: colors.brand.primary }}>
              메일을 다시 보냈습니다.
            </span>
          ) : null}
          {state === 'failed' ? (
            <span
              className="text-15"
              style={{ color: colors.status.notRecommend }}
            >
              메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.
            </span>
          ) : null}
        </div>
      </Card>
    </main>
  );
}
