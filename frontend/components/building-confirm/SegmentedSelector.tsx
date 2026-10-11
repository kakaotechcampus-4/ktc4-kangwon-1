import { colors } from '@/styles/tokens';

type SegmentedSelectorProps<T extends string> = {
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (value: T) => void;
  ariaLabel: string;
};

/** 붙어 있는 버튼 몇 개 중 하나를 고르는 선택기 — 주차·근린생활시설에서 같이 쓴다. */
export default function SegmentedSelector<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: SegmentedSelectorProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-grid w-fit max-w-full grid-flow-col auto-cols-fr self-start overflow-hidden rounded-lg border"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      {options.map((option, index) => {
        const isSelected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(option.value)}
            className="min-h-[52px] min-w-[96px] px-6 text-base whitespace-nowrap"
            style={{
              borderLeft:
                index === 0 ? 'none' : `1px solid ${colors.neutral.border}`,
              backgroundColor: isSelected
                ? colors.brand.dark
                : colors.neutral.white,
              color: isSelected ? colors.neutral.white : colors.text.secondary,
              fontWeight: isSelected ? 600 : 500,
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
