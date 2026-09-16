import { colors } from '@/styles/tokens';

type ProgressBarColor = 'primary' | 'danger' | 'warning' | 'muted';

type ProgressBarProps = {
  value: number;
  color?: ProgressBarColor;
  className?: string;
};

// muted는 primary와 같은 브랜드 계열의 어두운 톤이다. 추천/비추천을 색상으로
// 구분하되 위험(danger)만큼 강하게 주장하지 않아야 하는 막대에 쓴다.
const fillColors: Record<ProgressBarColor, string> = {
  primary: colors.brand.primary,
  danger: colors.status.notRecommend,
  warning: colors.accent.orange,
  muted: colors.brand.dark,
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
