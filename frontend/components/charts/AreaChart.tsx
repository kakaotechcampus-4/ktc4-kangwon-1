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
  // true면 peaks와 별개로 data의 모든 포인트 위에 값을 라벨로 찍는다(선택적
  // 옵트인 — 기본값 false라 이 prop을 넘기지 않는 기존 호출부는 전과 완전히
  // 동일하게 렌더링된다). 라벨 크기/표시 여부는 CSS 클래스
  // (area-chart-point-label*)로만 제어해, 이 prop을 쓰는 쪽에서
  // <style jsx global>로 반응형을 관리할 수 있게 한다.
  showPointLabels?: boolean;
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

type PointLabelContentProps = {
  viewBox?: { x?: number; y?: number };
  value: number;
  isFirst: boolean;
  isLast: boolean;
};

// recharts의 label={{ value, fontSize, fill, ... }} 형태는 값을 인라인 SVG
// 속성으로 굳혀버려 반응형 clamp()를 못 먹인다. content 함수로 직접 <text>를
// 그리고 className만 실어 보내, 크기/표시 여부는 전부 CSS(호출부의
// <style jsx global>)가 결정하게 한다.
function PointLabelContent({
  viewBox,
  value,
  isFirst,
  isLast,
}: PointLabelContentProps) {
  const x = viewBox?.x ?? 0;
  const y = viewBox?.y ?? 0;
  const emphasisClass = isLast
    ? 'area-chart-point-label-last'
    : isFirst
      ? 'area-chart-point-label-first'
      : 'area-chart-point-label-mid';
  // 첫/마지막 포인트는 x축 양 끝에 붙어 있어 textAnchor="middle"을 쓰면
  // 라벨 절반이 차트 영역 밖으로 잘린다. 끝 포인트는 안쪽으로만 자라도록
  // anchor를 바꾼다(첫 포인트는 오른쪽으로, 마지막 포인트는 왼쪽으로).
  const textAnchor = isFirst ? 'start' : isLast ? 'end' : 'middle';

  return (
    <text
      x={x}
      y={y - (isLast ? 14 : 10)}
      textAnchor={textAnchor}
      className={`area-chart-point-label ${emphasisClass}`}
    >
      {value.toLocaleString('ko-KR')}
    </text>
  );
}

export default function AreaChart({
  data,
  height = 232,
  highlight,
  peaks = [],
  valueSuffix = '',
  showPointLabels = false,
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

          {showPointLabels &&
            data.map((point, index) => {
              const isFirst = index === 0;
              const isLast = index === data.length - 1;

              return (
                <ReferenceDot
                  key={`point-label-${point.label}`}
                  x={point.label}
                  y={point.value}
                  r={isLast ? 5 : 3}
                  fill={colors.brand.dark}
                  stroke={colors.neutral.white}
                  strokeWidth={2}
                  label={{
                    position: 'top',
                    content: (contentProps: unknown) => (
                      <PointLabelContent
                        {...(contentProps as PointLabelContentProps)}
                        value={point.value}
                        isFirst={isFirst}
                        isLast={isLast}
                      />
                    ),
                  }}
                />
              );
            })}

          <Tooltip
            content={<ChartTooltip valueSuffix={valueSuffix} />}
            position={{ y: Math.max(0, height - 80) }}
            cursor={{ stroke: colors.neutral.border }}
            wrapperStyle={{ pointerEvents: 'none', zIndex: 10 }}
          />
        </RechartsAreaChart>
      </ResponsiveContainer>

      {/*
        showPointLabels가 찍는 라벨(.area-chart-point-label*)의 스타일을 이
        컴포넌트 자신이 갖고 있어야, AreaChart를 쓰는 어느 파일에서든(현재
        FloatingPopulationSection.tsx, CompetitorAnalysisSection.tsx) 별도
        CSS를 복제하지 않고 그대로 재사용된다. <style jsx global>은 이걸
        렌더링하는 컴포넌트의 마운트 생명주기를 따라 주입/정리되므로,
        호출부 파일에 이 규칙을 옮겨 적으면 그 파일이 마운트되지 않은
        다른 탭에서는 스타일이 아예 안 붙는다 — 그래서 라벨을 실제로
        그리는 이 파일이 스타일도 함께 소유한다.

        크기/색은 본문보다 작고 muted 톤으로 고정하고, 마지막 포인트만
        굵게 강조한다. 375px처럼 좁은 화면에서는 중간 포인트 라벨이 서로
        겹치기 쉬워 기본값을 숨김으로 두고, 640px 이상에서만 전부 보이게
        한다. showPointLabels를 안 쓰는 기존 호출부(v1 FootTrafficChart.tsx의
        peaks 방식)는 이 클래스를 렌더링하지 않으므로 영향이 없다.
      */}
      <style jsx global>{`
        .area-chart-point-label {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.000939),
            12px
          );
          fill: var(--color-gray-500);
        }
        .area-chart-point-label-last {
          font-size: clamp(
            12px,
            calc(12px + (100vw - 375px) * 0.000939),
            13px
          );
          font-weight: 700;
          fill: ${colors.brand.dark};
        }
        .area-chart-point-label-mid {
          display: none;
        }
        @media (min-width: 640px) {
          .area-chart-point-label-mid {
            display: block;
          }
        }
      `}</style>
    </div>
  );
}
