import type { ReactNode } from 'react';
import { colors } from '@/styles/tokens';
import type { BuildingField } from '@/lib/api/building';
import SourceBadge from './SourceBadge';

type BuildingFieldRowProps<T> = {
  label: string;
  field: BuildingField<T>;
  format: (value: T) => string;
  // 입력 칸을 보여줄지. 건축물대장에 없던 행은 편집 모드가 아니어도 항상 true로 넘긴다.
  editable: boolean;
  // editable일 때 값 대신 보여줄 입력 칸
  editor: ReactNode;
};

/** 수정 가능한 한 행 — 라벨 · 값(또는 입력 칸) · 출처 배지. 건축물대장에 없는 행은 주황 배경. */
export default function BuildingFieldRow<T>({
  label,
  field,
  format,
  editable,
  editor,
}: BuildingFieldRowProps<T>) {
  return (
    <div
      className="flex flex-col items-start gap-3 px-5 py-5 sm:min-h-[88px] sm:flex-row sm:items-center sm:gap-6 sm:px-10"
      style={{
        borderTop: `1px solid ${colors.neutral.border}`,
        backgroundColor:
          field.source === 'missing'
            ? `${colors.accent.orange}0F`
            : colors.neutral.white,
      }}
    >
      <p
        className="shrink-0 text-fluid-15-16 break-keep sm:w-[140px] xl:w-[200px]"
        style={{ color: colors.text.secondary }}
      >
        {label}
      </p>
      {/* 값과 출처 배지를 한 줄에 두되, 자리가 모자라면 배지를 아래 줄로 보낸다. */}
      <div className="flex w-full min-w-0 flex-1 flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-full">
          {editable ? (
            editor
          ) : (
            <p
              className="text-xl font-bold"
              style={{ color: colors.text.primary }}
            >
              {field.value === null ? '—' : format(field.value)}
            </p>
          )}
        </div>
        <SourceBadge
          source={field.source}
          registryText={
            field.registryValue === null ? null : format(field.registryValue)
          }
        />
      </div>
    </div>
  );
}
