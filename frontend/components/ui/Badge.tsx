import type { HTMLAttributes, ReactNode } from 'react';
import { DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

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
      className={`${dmMono.className} inline-flex shrink-0 items-center rounded-md px-2.5 py-1 text-[10px] tracking-[1.2px] whitespace-nowrap uppercase ${className}`}
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
