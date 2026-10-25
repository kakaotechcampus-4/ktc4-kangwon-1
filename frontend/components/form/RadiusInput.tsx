'use client';

import type { ChangeEvent } from 'react';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import { colors } from '@/styles/tokens';

type RadiusInputProps = {
  value: string;
  onChange: (value: string) => void;
};

export default function RadiusInput({ value, onChange }: RadiusInputProps) {
  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    // 반경은 숫자 하나만 의미가 있어서 숫자 이외 문자는 입력 즉시 걸러낸다.
    onChange(event.target.value.replace(/[^0-9]/g, ''));
  }

  return (
    <Card
      className="w-full gap-4"
      style={{
        padding: '32px',
        borderRadius: '24px',
        borderWidth: '0px',
      }}
    >
      <p className="text-xl font-bold" style={{ color: colors.brand.dark }}>
        2. 반경 입력
      </p>

      <div className="flex flex-col items-start gap-2">
        <label
          htmlFor="analysis-radius"
          className="text-15 font-medium text-gray-500"
        >
          분석 반경
        </label>
        <div className="flex w-full items-center gap-2">
          <div className="w-full max-w-56">
            <Input
              id="analysis-radius"
              inputMode="numeric"
              value={value}
              onChange={handleChange}
              placeholder="예: 100, 300, 500"
            />
          </div>
          <span className="text-base text-gray-500">m</span>
        </div>
      </div>
    </Card>
  );
}
