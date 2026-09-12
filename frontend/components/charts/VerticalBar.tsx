'use client';

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import { colors } from '@/styles/tokens';

export type VerticalBarItem = {
  label: string;
  value: number;
  color: string;
};

type VerticalBarProps = {
  items: VerticalBarItem[];
  height?: number;
  valueSuffix?: string;
  maxFillRatio?: number;
};

const AXIS_TEXT_COLOR = 'var(--color-gray-500)';

export default function VerticalBar({
  items,
  height = 260,
  valueSuffix = '',
  maxFillRatio = 0.85,
}: VerticalBarProps) {
  const dataMax = Math.max(...items.map((item) => item.value), 0);
  const domainMax = dataMax > 0 ? dataMax / maxFillRatio : 1;

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={items}
          margin={{ top: 32, right: 8, bottom: 8, left: 8 }}
        >
          <YAxis hide domain={[0, domainMax]} />
          <XAxis
            dataKey="label"
            axisLine={{ stroke: colors.neutral.border }}
            tickLine={false}
            tick={{ fill: AXIS_TEXT_COLOR, fontSize: 13 }}
            interval={0}
          />
          <Bar
            dataKey="value"
            radius={[6, 6, 0, 0]}
            maxBarSize={64}
            isAnimationActive={false}
          >
            {items.map((item) => (
              <Cell key={item.label} fill={item.color} />
            ))}
            <LabelList
              dataKey="value"
              position="top"
              formatter={(value) => `${value ?? ''}${valueSuffix}`}
              style={{
                fill: colors.neutral.black,
                fontSize: 15,
                fontWeight: 700,
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
