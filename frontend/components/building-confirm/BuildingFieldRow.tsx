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
  showSource?: boolean;
};

/** 수정 가능한 한 행 — 라벨 · 값(또는 입력 칸) · 출처 배지. 건축물대장에 없는 행은 주황 배경. */
export default function BuildingFieldRow<T>({
  label,
  field,
  format,
  editable,
  editor,
  showSource = true,
}: BuildingFieldRowProps<T>) {
  return (
    <div
      className="grid min-w-0 grid-cols-1 items-start gap-x-6 gap-y-2.5 px-4 py-4 sm:grid-cols-[minmax(150px,220px)_minmax(0,1fr)] sm:gap-y-3 sm:px-8 sm:py-5 lg:px-10"
      style={{
        borderTop: `1px solid ${colors.neutral.border}`,
        backgroundColor:
          field.source === 'missing'
            ? `${colors.accent.orange}0F`
            : colors.neutral.white,
      }}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 sm:pt-3">
        <p
          className="min-w-0 text-sm sm:text-base"
          style={{ color: colors.text.secondary }}
        >
          {label}
        </p>
        {showSource && field.source !== 'missing' && (
          <SourceBadge
            source={field.source}
            registryText={
              field.registryValue === null ? null : format(field.registryValue)
            }
          />
        )}
      </div>
      <div className="flex w-full min-w-0 items-center sm:col-start-2">
        {editable ? (
          <div className="w-full min-w-0">{editor}</div>
        ) : (
          <p
            className="text-xl font-bold"
            style={{ color: colors.text.primary }}
          >
            {field.value === null ? '—' : format(field.value)}
          </p>
        )}
      </div>
      {showSource && field.source === 'missing' && (
        <div className="min-w-0 sm:col-start-2">
          <SourceBadge
            source={field.source}
            registryText={
              field.registryValue === null ? null : format(field.registryValue)
            }
          />
        </div>
      )}
    </div>
  );
}
