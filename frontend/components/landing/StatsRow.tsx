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

export default function StatsRow({ stats = defaultStats }: StatsRowProps) {
  return (
    <div className="flex w-full flex-col items-center pb-16">
      <div className="flex w-full max-w-[1185px] gap-[60px]">
        {stats.map(({ id, label, value, unit, accent }) => {
          const accentColor =
            accent === 'primary' ? colors.brand.primary : colors.brand.dark;

          return (
            <div
              key={id}
              className="relative flex w-[251.25px] shrink-0 flex-col overflow-hidden rounded-xl border p-6"
              style={{
                backgroundColor: colors.neutral.white,
                borderColor: colors.neutral.border,
              }}
            >
              <span
                className="absolute size-20 rounded-full opacity-5"
                style={{ backgroundColor: accentColor, top: -24, right: -23 }}
              />

              <p className="text-sm leading-[21px] tracking-[1.96px] text-gray-400 uppercase">
                {label}
              </p>

              <div className="flex items-baseline gap-1.5 pt-3">
                <span
                  className="text-[35px] leading-[52.5px] font-bold"
                  style={{ color: accentColor }}
                >
                  {value}
                </span>
                <span className="text-sm font-medium text-gray-400">
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
