import { Outfit } from 'next/font/google';
import Card from '@/components/ui/Card';
import AreaChart from '@/components/charts/AreaChart';
import HorizontalBar from '@/components/charts/HorizontalBar';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const CORE_TARGET_AGE_GROUPS = new Set(['20대', '30대']);

const panelStyle = {
  backgroundColor: colors.neutral.background,
  borderColor: colors.neutral.border,
};

export default function FootTrafficChart() {
  const { dailyAverage, hourly, peakLabel, ageGroups, source } =
    mockReportData.footTraffic;

  const areaData = hourly.map((point) => ({
    label: point.hour,
    value: point.count,
  }));

  const topTwo = [...hourly].sort((a, b) => b.count - a.count).slice(0, 2);
  const peakHours = new Set(topTwo.map((point) => point.hour));
  const peakPoints = hourly.filter((point) => peakHours.has(point.hour));
  const peaks = peakPoints.map((point) => ({
    label: point.hour,
    value: point.count,
  }));

  const businessHoursStart = hourly.find((point) => point.hour === '10시');
  const businessHoursEnd = hourly.find((point) => point.hour === '20시');
  const highlight =
    businessHoursStart && businessHoursEnd
      ? {
          from: businessHoursStart.hour,
          to: businessHoursEnd.hour,
          text: peakLabel,
        }
      : undefined;

  const ageItems = ageGroups.map((group) => ({
    label: group.label,
    value: group.percent,
    emphasis: CORE_TARGET_AGE_GROUPS.has(group.label),
  }));

  return (
    <div className="w-full px-8 pt-8">
      <Card
        className="w-full"
        style={{
          padding: '28px 32px',
          borderRadius: '12px',
          borderWidth: '1px',
          boxShadow: 'none',
        }}
      >
        <div className="flex w-full items-center justify-between">
          <h2
            className={`${outfit.className} text-[25px] font-bold`}
            style={{ color: colors.neutral.black }}
          >
            유동인구 분포도
          </h2>
          <p
            className="text-sm font-bold"
            style={{ color: colors.brand.primary }}
          >
            일평균 {dailyAverage.toLocaleString()}명
          </p>
        </div>

        <div
          className="mt-7 flex w-full flex-col gap-4 rounded-[10px] border p-5"
          style={panelStyle}
        >
          <h3
            className={`${outfit.className} text-lg font-bold`}
            style={{ color: colors.neutral.black }}
          >
            시간대별 유동인구
          </h3>
          <AreaChart
            data={areaData}
            height={232}
            valueSuffix="명"
            highlight={highlight}
            peaks={peaks}
          />
        </div>

        <div
          className="mt-6 flex w-full flex-col gap-4 rounded-[10px] border p-5"
          style={panelStyle}
        >
          <h3
            className={`${outfit.className} text-lg font-bold`}
            style={{ color: colors.neutral.black }}
          >
            연령대별 유동인구
          </h3>
          <HorizontalBar items={ageItems} />
        </div>

        <p className="mt-5 text-xs text-gray-400">출처: {source}</p>
      </Card>
    </div>
  );
}
