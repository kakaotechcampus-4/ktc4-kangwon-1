import { colors } from '@/styles/tokens';

export type HorizontalBarItem = {
  label: string;
  value: number;
  emphasis?: boolean;
};

type HorizontalBarProps = {
  items: HorizontalBarItem[];
  max?: number;
  valueSuffix?: string;
};

export default function HorizontalBar({
  items,
  max = 100,
  valueSuffix = '%',
}: HorizontalBarProps) {
  return (
    <div className="flex w-full flex-col gap-3.5">
      {items.map(({ label, value, emphasis }) => {
        const percent = Math.min(100, Math.max(0, (value / max) * 100));

        return (
          <div key={label} className="flex w-full items-center gap-3">
            <p
              className="w-16 shrink-0 text-sm"
              style={{ color: colors.neutral.black }}
            >
              {label}
            </p>
            <div className="h-4 flex-1 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${percent}%`,
                  backgroundColor: emphasis
                    ? colors.brand.primary
                    : `${colors.brand.dark}66`,
                }}
              />
            </div>
            <p
              className={`w-12 shrink-0 text-right text-sm font-bold ${
                emphasis ? '' : 'text-gray-500'
              }`}
              style={emphasis ? { color: colors.brand.primary } : undefined}
            >
              {value}
              {valueSuffix}
            </p>
          </div>
        );
      })}
    </div>
  );
}
