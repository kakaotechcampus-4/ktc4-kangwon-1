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
      className={`relative flex flex-col overflow-hidden rounded-2xl border-[1.5px] p-7 shadow-[0px_1px_4px_0px_rgba(0,0,0,0.04)] ${className}`}
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
