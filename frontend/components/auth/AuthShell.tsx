'use client';

import type { ReactNode } from 'react';
import Header from '@/components/layout/Header';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

/** 로그인·가입·비밀번호 화면이 공유하는 틀. 가운데 한 장짜리 카드다. */
export default function AuthShell({
  eyebrow,
  title,
  description,
  children,
  footer,
}: {
  eyebrow: string;
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
      <main className="flex flex-1 justify-center px-4 pt-16 pb-24">
        <div className="flex w-full max-w-[480px] flex-col gap-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <p
              className="text-sm font-bold tracking-[0.08em]"
              style={{ color: colors.brand.primary }}
            >
              {eyebrow}
            </p>
            <h1
              className="text-3xl font-extrabold tracking-[-0.03em] break-keep"
              style={{ color: colors.brand.dark }}
            >
              {title}
            </h1>
            {description ? (
              <p className="text-base break-keep text-[#4B5866]">
                {description}
              </p>
            ) : null}
          </div>
          <Card className="gap-6">{children}</Card>
          {footer ? (
            <div className="text-center text-15 text-[#4B5866] [&_a]:font-bold [&_a]:text-[#2453D6]">
              {footer}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
