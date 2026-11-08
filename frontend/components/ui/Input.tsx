import type { InputHTMLAttributes } from 'react';
import { colors } from '@/styles/tokens';

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export default function Input({ className = '', style, ...rest }: InputProps) {
  return (
    <input
      className={`w-full rounded-xl border-[1.5px] px-3.5 py-3 text-sm outline-none placeholder:text-gray-400 focus:border-[#2453D6] sm:px-4 sm:py-3.5 sm:text-base ${className}`}
      style={{
        backgroundColor: colors.neutral.white,
        borderColor: '#D5DEE7',
        color: colors.brand.dark,
        ...style,
      }}
      {...rest}
    />
  );
}
