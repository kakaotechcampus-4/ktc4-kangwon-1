import { colors } from '@/styles/tokens';

type ProgressBarColor = 'primary' | 'danger';

type ProgressBarProps = {
  value: number;
  color?: ProgressBarColor;
  className?: string;
};

const fillColors: Record<ProgressBarColor, string> = {
  primary: colors.brand.primary,
  danger: colors.status.notRecommend,
};

export default function ProgressBar({
  value,
  color = 'primary',
  className = '',
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div
      className={`h-2 w-full overflow-hidden rounded-full ${className}`}
      style={{ backgroundColor: colors.neutral.border }}
    >
      <div
        className="h-full rounded-full"
        style={{ width: `${clamped}%`, backgroundColor: fillColors[color] }}
      />
    </div>
  );
}
