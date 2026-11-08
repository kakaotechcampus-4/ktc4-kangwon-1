'use client';

import type { ReactNode } from 'react';
import { Check } from 'lucide-react';
import { colors } from '@/styles/tokens';

export default function Checkbox({
  id,
  checked,
  onChange,
  invalid = false,
  children,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  invalid?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="relative flex size-5 shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={invalid || undefined}
          className="size-5 cursor-pointer appearance-none rounded-[5px] border-[1.5px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2453D6]"
          style={{
            backgroundColor: checked
              ? colors.brand.primary
              : colors.neutral.white,
            borderColor: invalid
              ? colors.status.notRecommend
              : checked
                ? colors.brand.primary
                : '#99A6B2',
          }}
        />
        {checked ? (
          <Check
            aria-hidden="true"
            size={14}
            strokeWidth={3}
            className="pointer-events-none absolute inset-0 m-auto"
            style={{ color: colors.neutral.white }}
          />
        ) : null}
      </span>
      <label
        htmlFor={id}
        className="cursor-pointer text-15 break-keep"
        style={{ color: colors.brand.dark }}
      >
        {children}
      </label>
    </div>
  );
}
