import type { HTMLAttributes, ReactNode } from 'react';
import { colors } from '@/styles/tokens';

type CardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
};

export default function Card({
  className = '',
  style,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={`relative flex flex-col overflow-hidden rounded-3xl border p-7 shadow-[0px_18px_40px_0px_rgba(16,35,58,0.06)] ${className}`}
      style={{
        backgroundColor: colors.neutral.white,
        borderColor: colors.neutral.border,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
