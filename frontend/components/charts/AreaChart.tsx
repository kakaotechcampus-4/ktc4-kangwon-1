'use client';

import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts';
import { colors } from '@/styles/tokens';

export type AreaChartPoint = {
  label: string;
  value: number;
};

export type AreaChartHighlight = {
  from: string;
  to: string;
  text: string;
};

export type AreaChartPeak = {
  label: string;
  value: number;
};

type AreaChartProps = {
  data: AreaChartPoint[];
  height?: number;
  highlight?: AreaChartHighlight;
  peaks?: AreaChartPeak[];
  valueSuffix?: string;
};

const AXIS_TEXT_COLOR = 'var(--color-gray-500)';

type ChartTooltipPayloadEntry = {
  payload: AreaChartPoint;
};

type ChartTooltipProps = {
  active?: boolean;
  payload?: ChartTooltipPayloadEntry[];
  valueSuffix: string;
};

function ChartTooltip({ active, payload, valueSuffix }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0].payload;

  return (
    <div
      className="rounded-md border px-3 py-1.5 text-xs whitespace-nowrap shadow-sm"
      style={{
        backgroundColor: colors.neutral.white,
        borderColor: colors.neutral.border,
      }}
    >
      <span style={{ color: colors.neutral.black }}>{point.label}</span>{' '}
      <span className="font-bold" style={{ color: colors.brand.dark }}>
        {point.value.toLocaleString()}
        {valueSuffix}
      </span>
    </div>
  );
}

export default function AreaChart({
  data,
  height = 232,
  highlight,
  peaks = [],
  valueSuffix = '',
}: AreaChartProps) {
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsAreaChart
          data={data}
          margin={{ top: 32, right: 8, bottom: 0, left: 8 }}
        >
          <defs>
            <linearGradient id="areaChartFill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={colors.brand.dark}
                stopOpacity={0.35}
              />
              <stop
                offset="100%"
                stopColor={colors.brand.dark}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>

          {highlight && (
            <ReferenceArea
              x1={highlight.from}
              x2={highlight.to}
              fill={colors.accent.orange}
              fillOpacity={0.12}
              stroke="none"
              ifOverflow="visible"
              label={{
                value: highlight.text,
                position: 'insideTop',
                fill: colors.accent.orange,
                fontSize: 11,
                fontWeight: 700,
              }}
            />
          )}

          <CartesianGrid vertical={false} horizontal={false} />

          <XAxis
            dataKey="label"
            axisLine={{ stroke: colors.neutral.border }}
            tickLine={false}
            tick={{ fill: AXIS_TEXT_COLOR, fontSize: 11 }}
            interval={0}
            padding={{ left: 0, right: 0 }}
          />

          <Area
            type="monotone"
            dataKey="value"
            stroke={colors.brand.dark}
            strokeWidth={2}
            fill="url(#areaChartFill)"
            dot={false}
            activeDot={{
              r: 4,
              fill: colors.brand.dark,
              stroke: colors.neutral.white,
              strokeWidth: 2,
            }}
            isAnimationActive={false}
          />

          {peaks.map((peak) => (
            <ReferenceDot
              key={peak.label}
              x={peak.label}
              y={peak.value}
              r={3}
              fill={colors.brand.dark}
              stroke={colors.neutral.white}
              strokeWidth={2}
              label={{
                value: `${peak.value.toLocaleString()}${valueSuffix}`,
                position: 'top',
                fill: colors.brand.dark,
                fontSize: 12,
                fontWeight: 700,
              }}
            />
          ))}

          <Tooltip
            content={<ChartTooltip valueSuffix={valueSuffix} />}
            position={{ y: Math.max(0, height - 80) }}
            cursor={{ stroke: colors.neutral.border }}
            wrapperStyle={{ pointerEvents: 'none', zIndex: 10 }}
          />
        </RechartsAreaChart>
      </ResponsiveContainer>
    </div>
  );
}
