import type { HTMLAttributes, ReactNode } from 'react';
import { pretendard } from '@/styles/fonts';
import { colors } from '@/styles/tokens';

const dmMono = pretendard;

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode;
};

export default function Badge({
  className = '',
  style,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={`${dmMono.className} inline-flex shrink-0 items-center rounded-md px-2.5 py-1 text-10 tracking-[1.2px] whitespace-nowrap uppercase ${className}`}
      style={{
        backgroundColor: `${colors.brand.primary}1A`,
        color: colors.brand.primary,
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}
