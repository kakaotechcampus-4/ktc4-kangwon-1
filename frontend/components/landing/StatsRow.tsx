import { colors } from '@/styles/tokens';

type Stat = {
  id: string;
  label: string;
  value: string;
  unit: string;
  accent: 'primary' | 'dark';
};

const defaultStats: Stat[] = [
  {
    id: 'market-data',
    label: '분석 상권 데이터',
    value: '12,480',
    unit: '건',
    accent: 'dark',
  },
  {
    id: 'store-count',
    label: '분석 점포 수',
    value: '3,840',
    unit: '개',
    accent: 'primary',
  },
  {
    id: 'competition',
    label: '평균 업종 경쟁도',
    value: '89',
    unit: '%',
    accent: 'dark',
  },
  {
    id: 'accuracy',
    label: '예측 정확도',
    value: '94',
    unit: '%',
    accent: 'primary',
  },
];

type StatsRowProps = {
  stats?: Stat[];
};

// 768px에서 min, 1440px에서 max가 되도록 선형 보간한다. max는 기존 디자인 값과
// 동일해 1440px 이상에서는 clamp 상한에 고정되어 기존 화면이 그대로 유지되고,
// 그 아래로는 미디어 쿼리 없이 한 수식으로 끊김 없이 줄어든다.
const fluid = (min: number, max: number) =>
  `clamp(${min}px, calc(${min}px + (100vw - 768px) * ${(
    (max - min) /
    672
  ).toFixed(5)}), ${max}px)`;

export default function StatsRow({ stats = defaultStats }: StatsRowProps) {
  return (
    <div
      className="flex w-full flex-col items-center pb-16"
      style={{ paddingInline: fluid(24, 127.5) }}
    >
      <div
        className="flex w-full max-w-[1185px]"
        style={{ gap: fluid(20, 60) }}
      >
        {stats.map(({ id, label, value, unit, accent }) => {
          const accentColor =
            accent === 'primary' ? colors.brand.primary : colors.brand.dark;

          return (
            <div
              key={id}
              className="relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border"
              style={{
                backgroundColor: colors.neutral.white,
                borderColor: colors.neutral.border,
                padding: fluid(14, 24),
              }}
            >
              <span
                className="absolute size-20 rounded-full opacity-5"
                style={{ backgroundColor: accentColor, top: -24, right: -23 }}
              />

              <p
                className="text-gray-400 uppercase"
                style={{
                  fontSize: fluid(10, 14),
                  lineHeight: fluid(15, 21),
                  letterSpacing: fluid(1.2, 1.96),
                }}
              >
                {label}
              </p>

              <div className="flex items-baseline gap-1.5 pt-3">
                <span
                  className="font-bold"
                  style={{
                    color: accentColor,
                    fontSize: fluid(22, 35),
                    lineHeight: fluid(33, 52.5),
                  }}
                >
                  {value}
                </span>
                <span
                  className="font-medium text-gray-400"
                  style={{ fontSize: fluid(10, 14) }}
                >
                  {unit}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <p className="pt-[30px] text-xs text-gray-400">
        ※ 수치는 프로토타입 시연용 목업 데이터입니다.
      </p>
    </div>
  );
}
