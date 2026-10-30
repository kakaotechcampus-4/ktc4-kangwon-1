import { AlertTriangle } from 'lucide-react';
import { colors } from '@/styles/tokens';
import type { FieldSource } from '@/lib/api/building';

type SourceBadgeProps = {
  source: FieldSource;
  // 건축물대장 원래 값을 화면에 보여줄 문자열. 원래 값이 없으면 null.
  registryText: string | null;
};

/** 행별 값의 출처 — 건축물대장 / 건축물대장에 없음 / 직접 수정·입력. */
export default function SourceBadge({
  source,
  registryText,
}: SourceBadgeProps) {
  const base =
    'inline-flex max-w-full shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-13 font-medium sm:whitespace-nowrap';

  if (source === 'registry') {
    return (
      <span
        className={base}
        style={{
          backgroundColor: `${colors.brand.primary}14`,
          color: colors.brand.primary,
        }}
      >
        건축물대장
      </span>
    );
  }

  if (source === 'missing') {
    return (
      <span
        className={`${base} font-semibold`}
        style={{
          backgroundColor: `${colors.accent.orange}1F`,
          color: colors.accent.orange,
        }}
      >
        <AlertTriangle size={14} />
        건축물대장에 없어요 · 알려주세요
      </span>
    );
  }

  return (
    <span
      className={`${base} border`}
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
        color: colors.text.secondary,
      }}
    >
      {registryText === null
        ? '직접 입력'
        : `직접 수정 · 건축물대장: ${registryText}`}
    </span>
  );
}
