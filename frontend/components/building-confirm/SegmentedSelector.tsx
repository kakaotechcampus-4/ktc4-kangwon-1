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
      className="grid w-full grid-cols-2 gap-px self-start overflow-hidden rounded-lg border [&>:last-child:nth-child(odd)]:col-span-2 @min-[28rem]:inline-grid @min-[28rem]:w-fit @min-[28rem]:max-w-full @min-[28rem]:grid-flow-col @min-[28rem]:auto-cols-fr @min-[28rem]:grid-cols-none @min-[28rem]:[&>:last-child:nth-child(odd)]:col-span-1"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.border,
      }}
    >
      {options.map((option) => {
        const isSelected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(option.value)}
            className="min-h-[52px] min-w-[72px] px-4 text-base whitespace-nowrap sm:min-w-[88px] sm:px-5"
            style={{
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
