import type { ReactNode } from 'react';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

type ConfirmLayoutProps = {
  children: ReactNode;
  actions: ReactNode;
  aside: ReactNode;
};

export default function ConfirmLayout({
  children,
  actions,
  aside,
}: ConfirmLayoutProps) {
  return (
    // 좁은 화면에서는 안내 패널을 확인 카드 아래로 내린다.
    <div className="grid w-full grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-10 xl:grid-cols-[minmax(0,1fr)_440px]">
      <Card
        className="w-full gap-0 [--building-radius:18px] sm:[--building-radius:24px]"
        style={{
          padding: 0,
          borderRadius: 'var(--building-radius)',
          borderWidth: '0px',
        }}
      >
        {children}
        <div
          className="flex flex-col-reverse gap-3 px-4 py-4 sm:flex-row sm:justify-end sm:gap-4 sm:px-10 sm:py-8"
          style={{ borderTop: `1px solid ${colors.neutral.border}` }}
        >
          {actions}
        </div>
      </Card>
      {aside}
    </div>
  );
}
