'use client';

import { Bar, BarChart, ResponsiveContainer, XAxis } from 'recharts';
import { colors } from '@/styles/tokens';

export type GroupedBarSeries = {
  key: string;
  color: string;
};

export type GroupedBarDatum = {
  label: string;
  [seriesKey: string]: string | number;
};

type GroupedBarProps = {
  data: GroupedBarDatum[];
  series: GroupedBarSeries[];
  height?: number;
};

const AXIS_TEXT_COLOR = 'var(--color-gray-500)';

export default function GroupedBar({
  data,
  series,
  height = 260,
}: GroupedBarProps) {
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 16, right: 8, bottom: 8, left: 8 }}
          barGap={4}
          barCategoryGap="28%"
        >
          <XAxis
            dataKey="label"
            axisLine={{ stroke: colors.neutral.border }}
            tickLine={false}
            tick={{ fill: AXIS_TEXT_COLOR, fontSize: 12 }}
            interval={0}
          />
          {series.map((item) => (
            <Bar
              key={item.key}
              dataKey={item.key}
              fill={item.color}
              radius={[4, 4, 4, 4]}
              maxBarSize={56}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
