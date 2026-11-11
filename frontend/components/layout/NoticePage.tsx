import type { ReactNode } from 'react';
import Header from '@/components/layout/Header';
import { colors } from '@/styles/tokens';

export default function NoticePage({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="mx-auto flex w-full max-w-[880px] flex-col gap-8 px-4 pt-14 pb-24 sm:px-8">
        <div className="flex flex-col gap-3">
          <p
            className="text-sm font-bold tracking-[0.08em]"
            style={{ color: colors.brand.primary }}
          >
            {eyebrow}
          </p>
          <h1
            className="font-extrabold tracking-[-0.04em] break-keep wrap-anywhere"
            style={{
              color: colors.brand.dark,
              fontSize: 'clamp(26px, 3vw, 42px)',
            }}
          >
            {title}
          </h1>
          <p className="text-base break-keep wrap-anywhere text-[#4B5866]">
            {description}
          </p>
        </div>
        {children}
      </main>
    </div>
  );
}
