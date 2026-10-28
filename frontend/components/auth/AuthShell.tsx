'use client';

import type { ReactNode } from 'react';
import Header from '@/components/layout/Header';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

/** 로그인·가입·비밀번호 화면이 공유하는 틀. 가운데 한 장짜리 카드다. */
export default function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="flex flex-1 justify-center px-6 py-14">
        <div className="flex w-full max-w-[420px] flex-col gap-5">
          <Card className="gap-6">
            <div className="flex flex-col gap-2">
              <h1
                className="text-26 font-bold"
                style={{ color: colors.neutral.black }}
              >
                {title}
              </h1>
              {description ? (
                <p className="text-15" style={{ color: colors.text.secondary }}>
                  {description}
                </p>
              ) : null}
            </div>
            {children}
          </Card>
          {footer ? (
            <div
              className="text-center text-15"
              style={{ color: colors.text.secondary }}
            >
              {footer}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
