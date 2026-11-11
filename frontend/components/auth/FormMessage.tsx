'use client';

import { colors } from '@/styles/tokens';

/** 폼 하나당 메시지 한 줄. 성공·실패를 같은 자리에 둬서 눈이 찾아다니지 않게 한다. */
export default function FormMessage({
  tone,
  id,
  children,
}: {
  tone: 'error' | 'success';
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <p
      id={id}
      role={tone === 'error' ? 'alert' : 'status'}
      className="text-15 break-keep wrap-anywhere"
      style={{
        color:
          tone === 'error' ? colors.status.notRecommend : colors.brand.primary,
      }}
    >
      {children}
    </p>
  );
}
