import Link from 'next/link';
import type {
  ButtonHTMLAttributes,
  ComponentProps,
  CSSProperties,
  ReactNode,
} from 'react';
import { colors } from '@/styles/tokens';

type ButtonVariant = 'primary' | 'outline';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

type ButtonLinkProps = ComponentProps<typeof Link> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

const baseClassName =
  'inline-flex shrink-0 items-center justify-center rounded-xl text-sm transition-opacity hover:opacity-90';

const variantClassNames: Record<ButtonVariant, string> = {
  primary: 'px-[28px] py-[14px] font-bold',
  outline: 'px-[20px] py-[14px] font-semibold border-[1.5px]',
};

const variantStyles: Record<ButtonVariant, CSSProperties> = {
  primary: {
    backgroundColor: colors.brand.primary,
    color: colors.neutral.white,
    boxShadow: `0px 8px 18px 0px ${colors.brand.primary}33`,
  },
  outline: {
    backgroundColor: colors.neutral.white,
    borderColor: colors.brand.dark,
    color: colors.brand.dark,
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
      className={`${baseClassName} ${variantClassNames[variant]} ${className}`}
      style={{ ...variantStyles[variant], ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = 'primary',
  className = '',
  style,
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link
      className={`${baseClassName} ${variantClassNames[variant]} ${className}`}
      style={{ ...variantStyles[variant], ...style }}
      {...rest}
    >
      {children}
    </Link>
  );
}
