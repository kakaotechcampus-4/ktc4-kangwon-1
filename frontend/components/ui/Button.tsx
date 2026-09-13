import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';
import { colors } from '@/styles/tokens';

type ButtonVariant = 'primary' | 'outline';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

const variantClassNames: Record<ButtonVariant, string> = {
  primary: 'px-[28px] py-[14px] font-semibold',
  outline: 'px-[20px] py-[14px] font-medium border',
};

const variantStyles: Record<ButtonVariant, CSSProperties> = {
  primary: {
    backgroundColor: colors.brand.dark,
    color: colors.neutral.white,
    boxShadow: `0px 4px 7px 0px ${colors.brand.dark}4D`,
  },
  outline: {
    backgroundColor: colors.neutral.white,
    borderColor: colors.neutral.border,
  },
};

export default function Button({
  variant = 'primary',
  className = '',
  style,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex shrink-0 items-center justify-center rounded-lg text-sm transition-opacity hover:opacity-90 ${variantClassNames[variant]} ${className}`}
      style={{ ...variantStyles[variant], ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}
