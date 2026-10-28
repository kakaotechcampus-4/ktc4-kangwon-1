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
      className="flex min-h-[88px] items-center gap-6 px-10 py-5"
      style={{
        borderTop: `1px solid ${colors.neutral.border}`,
        backgroundColor:
          field.source === 'missing'
            ? `${colors.accent.orange}0F`
            : colors.neutral.white,
      }}
    >
      <p
        className="w-[220px] shrink-0 text-base"
        style={{ color: colors.text.secondary }}
      >
        {label}
      </p>
      <div className="flex min-w-0 flex-1 items-center">
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
      {showSource && (
        <SourceBadge
          source={field.source}
          registryText={
            field.registryValue === null ? null : format(field.registryValue)
          }
        />
      )}
    </div>
  );
}
