'use client';

import { useState, type InputHTMLAttributes } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import Input from '@/components/ui/Input';
import { colors } from '@/styles/tokens';

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  /** 아래에 붙는 일치 여부 같은 안내. 직접 그려 넣는다. */
  status?: React.ReactNode;
};

/**
 * 비밀번호는 가려져 있어 오타를 쳐도 모른다. 눈 버튼으로 확인할 수 있게 한다.
 */
export default function PasswordField({
  label,
  hint,
  status,
  id,
  ...rest
}: Props) {
  const [visible, setVisible] = useState(false);
  const fieldId = id ?? rest.name ?? label;
  const hintId = hint ? `${fieldId}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={fieldId}
        className="text-15 font-medium"
        style={{ color: colors.text.primary }}
      >
        {label}
      </label>

      <div className="relative">
        <Input
          id={fieldId}
          type={visible ? 'text' : 'password'}
          aria-describedby={hintId}
          className="pr-11"
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? '비밀번호 숨기기' : '비밀번호 보기'}
          aria-pressed={visible}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg"
          style={{ color: colors.text.tertiary }}
        >
          {visible ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>

      {hint ? (
        <p
          id={hintId}
          className="text-13"
          style={{ color: colors.text.tertiary }}
        >
          {hint}
        </p>
      ) : null}
      {status}
    </div>
  );
}
