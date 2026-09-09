import { colors } from '@/styles/tokens';

type ProgressBarProps = {
  value: number;
  className?: string;
};

export default function ProgressBar({
  value,
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
        style={{ width: `${clamped}%`, backgroundColor: colors.brand.primary }}
      />
    </div>
  );
}
