import type { InputHTMLAttributes } from 'react';
import { colors } from '@/styles/tokens';

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export default function Input({ className = '', style, ...rest }: InputProps) {
  return (
    <input
      className={`w-full rounded-lg border px-3.5 py-3 text-base placeholder:text-gray-400 ${className}`}
      style={{
        backgroundColor: colors.neutral.white,
        borderColor: colors.neutral.border,
        color: colors.neutral.black,
        ...style,
      }}
      {...rest}
    />
  );
}
