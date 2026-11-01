'use client';

import type { InputHTMLAttributes } from 'react';
import Input from '@/components/ui/Input';
import { colors } from '@/styles/tokens';

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
};

export default function FormField({ label, hint, id, ...rest }: Props) {
  const fieldId = id ?? rest.name ?? label;
  const hintId = hint ? `${fieldId}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-15 font-medium text-gray-500">
        {label}
      </label>
      <Input id={fieldId} aria-describedby={hintId} {...rest} />
      {hint ? (
        <p
          id={hintId}
          className="text-13"
          style={{ color: colors.text.tertiary }}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}
