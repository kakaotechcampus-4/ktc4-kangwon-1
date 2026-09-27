'use client';

import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import AreaChart from '@/components/charts/AreaChart';
import DivergingBar from '@/components/report/DivergingBar';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { colors } from '@/styles/tokens';
import {
  mockReportData,
  type AgentStatus,
  type FloatingPopulationData,
  type ReliabilityLevel,
} from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

const fluid = (min: number, max: number) =>
  `clamp(${min}px, calc(${min}px + (100vw - 375px) * ${(
    (max - min) /
    1065
  ).toFixed(6)}), ${max}px)`;

/**
 * status에 따라 전체 섹션을 그릴지 결정한다. CompetitorAnalysisSection.tsx와
 * 동일한 원칙 — no_data/error는 data가 비어 있는 상태이므로 A~I 섹션을
 * 아예 그리지 않는다. 375/768/1024/1440 스크린샷은 'partial' 시나리오만
 * 담고 있고, no_data/error 분기는 코드 리뷰로 확인했다(한 줄짜리 상태
 * 비교라 별도 렌더 시나리오 없이도 충분하다고 판단).
 */
export function getSectionVisibility(
  status: AgentStatus
): 'visible' | 'hidden' {
  return status === 'no_data' || status === 'error' ? 'hidden' : 'visible';
}

export function shouldShowWarnings(status: AgentStatus): boolean {
  return status === 'partial';
}

function formatAgeLabel(key: string): string {
  return key === '60' ? '60대+' : `${key}대`;
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card
      className="fp-card w-full"
      style={{
        padding: 0,
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow:
          '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
      }}
    >
      <div
        className="fp-card-head flex w-full flex-col items-start"
        style={{ borderBottom: `1px solid ${colors.neutral.border}` }}
      >
        <p
          className={`fp-card-title ${outfit.className} font-bold`}
          style={{ color: colors.neutral.black }}
        >
          {title}
        </p>
        {description && (
          <p className="fp-card-desc text-gray-500">{description}</p>
        )}
      </div>
      <div className="fp-card-body flex w-full flex-col items-start">
        {children}
      </div>
    </Card>
  );
}

/** selection.applied가 dropped 배열을 통해 특정 섹션 부재를 설명해 줄 때 쓰는 안내 카드. */
function SelectionReasonNote({
  data,
  droppedKey,
  fallbackTitle,
}: {
  data: FloatingPopulationData;
  droppedKey: string;
  fallbackTitle: string;
}) {
  if (!data.selection.applied || !data.selection.dropped.includes(droppedKey)) {
    return null;
  }

  return (
    <SectionCard title={fallbackTitle}>
      <p className="fp-empty-note">{data.selection.reason}</p>
    </SectionCard>
  );
}

// reliability.level은 이 컴포넌트에서 색상 판단이 허용된 유일한 지표다
// (표본 신뢰도는 높을수록 실제로 좋다). 나머지 지수는 전부 중립색만 쓴다.
const RELIABILITY_COLOR: Record<ReliabilityLevel, string> = {
  high: colors.brand.primary,
  medium: colors.accent.orange,
  low: colors.status.notRecommend,
};
const RELIABILITY_LABEL: Record<ReliabilityLevel, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
};

/** 1. 유형 카드 */
function TypeHeaderCard({ data }: { data: FloatingPopulationData }) {
  const reliabilityColor = RELIABILITY_COLOR[data.reliability.level];

  return (
    <Card
      className="fp-type-card w-full"
      style={{
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow:
          '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
      }}
    >
      <div className="fp-type-head">
        <Badge
          style={{
            backgroundColor: `${colors.brand.primary}1A`,
            color: colors.brand.dark,
            fontFamily: 'inherit',
            textTransform: 'none',
            letterSpacing: 'normal',
            fontSize: fluid(16, 22),
            paddingInline: fluid(12, 18),
            paddingBlock: fluid(6, 9),
          }}
        >
          {data.type.label}
        </Badge>

        <div className="fp-type-badges">
          <Badge
            style={{
              backgroundColor: `${reliabilityColor}1A`,
              color: reliabilityColor,
              fontFamily: 'inherit',
              textTransform: 'none',
              letterSpacing: 'normal',
              fontSize: fluid(10, 12),
            }}
          >
            신뢰도 {RELIABILITY_LABEL[data.reliability.level]}
          </Badge>
          <Badge
            style={{
              backgroundColor: colors.neutral.background,
              color: 'var(--color-gray-500)',
              fontFamily: 'inherit',
              textTransform: 'none',
              letterSpacing: 'normal',
              fontSize: fluid(10, 12),
            }}
          >
            {data.reliability.trade_area_count}곳 중{' '}
            {data.reliability.covered_trade_areas}곳 자료 확보
          </Badge>
        </div>
      </div>

      <ul className="fp-type-reasons">
        {data.type.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </Card>
  );
}

/** 2. 핵심 stat */
function CoreStat({ data }: { data: FloatingPopulationData }) {
  const topPercent = 100 - data.benchmark.scale_percentile;

  return (
    <div className="fp-core-stats">
      <SectionCard title="하루 평균 유동인구">
        <p className={`fp-core-value ${dmMono.className}`}>
          <span style={{ color: colors.brand.dark }}>
            {Math.round(data.population.daily_avg).toLocaleString('ko-KR')}
          </span>
          <span className="fp-core-unit">명/일</span>
        </p>
      </SectionCard>
      <SectionCard title="상권 규모">
        <p className="fp-core-prefix">서울 상권 상위</p>
        <p className={`fp-core-value ${dmMono.className}`}>
          <span style={{ color: colors.brand.dark }}>{topPercent}</span>
          <span className="fp-core-unit">%</span>
        </p>
      </SectionCard>
    </div>
  );
}

const AGE_COLORS = [
  colors.brand.primary,
  colors.brand.dark,
  colors.accent.orange,
  `${colors.brand.primary}99`,
  `${colors.brand.dark}99`,
  `${colors.accent.orange}99`,
];

/** 4. 연령대별 분포 */
function AgeDistribution({ data }: { data: FloatingPopulationData }) {
  const ageKeys = Object.keys(data.population.age_share);
  const slices = ageKeys.map((key, i) => ({
    name: formatAgeLabel(key),
    value: data.population.age_share[key],
    color: AGE_COLORS[i % AGE_COLORS.length],
  }));
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  return (
    <SectionCard
      title="연령대별 분포"
      description="이 반경 유동인구의 연령대 구성과, 서울 평균 대비 각 연령대가 얼마나 많은지를 함께 보여줍니다."
    >
      <div className="fp-age-wrap">
        <div className="fp-age-donut">
          <div className="fp-donut-chart">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="92%"
                  paddingAngle={1}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {slices.map((slice) => (
                    <Cell key={slice.name} fill={slice.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="fp-donut-legend">
            {slices.map((slice) => (
              <div key={slice.name} className="fp-donut-legend-row">
                <span
                  className="fp-donut-swatch"
                  style={{ backgroundColor: slice.color }}
                />
                <span className="fp-donut-legend-name">{slice.name}</span>
                <span className={`fp-donut-legend-value ${dmMono.className}`}>
                  {((slice.value / total) * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="fp-age-index">
          <p className="fp-age-index-label">서울 평균 대비(1.0 기준)</p>
          {ageKeys.map((key) => (
            <DivergingBar
              key={key}
              eyebrow={formatAgeLabel(key)}
              value={data.benchmark.age_index[key] ?? null}
            />
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

/** 5. 분기별 추세 */
function TrendChart({ data }: { data: FloatingPopulationData }) {
  if (!data.trend) {
    return (
      <SelectionReasonNote
        data={data}
        droppedKey="trend"
        fallbackTitle="분기별 추세"
      />
    );
  }

  const points = data.trend.quarters.map((q) => ({
    label: q.period,
    value: Math.round(q.daily_avg),
  }));

  return (
    <SectionCard
      title="분기별 추세"
      description="분기마다 하루 평균 유동인구가 어떻게 바뀌어 왔는지 보여줍니다."
    >
      <div className="fp-chart-wrap">
        <AreaChart
          data={points}
          height={200}
          valueSuffix="명"
          showPointLabels
        />
      </div>
      <p className="fp-trend-caption">
        {/* qoq_change는 분기가 2개 미만이면 null이다(backend 스키마 그대로) —
            그 경우엔 "전분기 대비" 수치 없이 direction만 보여준다. */}
        {data.trend.qoq_change !== null && (
          <>
            전분기 대비 {data.trend.qoq_change > 0 ? '+' : ''}
            {data.trend.qoq_change}%,{' '}
          </>
        )}
        {data.trend.direction}
      </p>
    </SectionCard>
  );
}

/** 3. 반경별 인구 */
function RadiusProfileChart({ data }: { data: FloatingPopulationData }) {
  if (!data.radius_profile) {
    return (
      <SelectionReasonNote
        data={data}
        droppedKey="radius_profile"
        fallbackTitle="반경별 인구"
      />
    );
  }

  const points = data.radius_profile.points.map((p) => ({
    label: `${p.radius_m}m`,
    value: Math.round(p.daily_avg),
  }));

  return (
    <SectionCard
      title="반경별 인구"
      description="반경이 넓어질수록 하루 평균 유동인구가 어떻게 늘어나는지 보여줍니다."
    >
      <div className="fp-chart-wrap">
        <AreaChart
          data={points}
          height={200}
          valueSuffix="명"
          showPointLabels
        />
      </div>
      <p className="fp-radius-caption">
        50~100m 구간은 표본이 적어 추정 성격이 강합니다.
      </p>
      <p className="fp-radius-method">{data.radius_profile.method}</p>
    </SectionCard>
  );
}

/** 6. 집계 상권 목록 */
function TradeAreaList({ data }: { data: FloatingPopulationData }) {
  if (!data.trade_areas) {
    return (
      <SelectionReasonNote
        data={data}
        droppedKey="trade_areas"
        fallbackTitle="집계 상권 목록"
      />
    );
  }

  return (
    <SectionCard
      title="집계 상권 목록"
      description="이 지역을 나눈 조각들입니다. 동네 개수가 아닙니다."
    >
      <ul className="fp-trade-area-list">
        {data.trade_areas.map((area) => (
          <li key={area.name} className="fp-trade-area-row">
            <span className="fp-trade-area-name">{area.name}</span>
            {area.kind && (
              <Badge
                style={{
                  backgroundColor: colors.neutral.background,
                  color: 'var(--color-gray-500)',
                  fontFamily: 'inherit',
                  textTransform: 'none',
                  letterSpacing: 'normal',
                  fontSize: fluid(9, 11),
                }}
              >
                {area.kind}
              </Badge>
            )}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

export default function FloatingPopulationSection({
  data = mockReportData.floatingPopulation as FloatingPopulationData,
}: {
  data?: FloatingPopulationData;
}) {
  const visibility = getSectionVisibility(data.status);

  if (visibility === 'hidden') {
    return (
      <div className="fp-root fp-root-empty">
        <p className="fp-empty-note">
          {data.status === 'error'
            ? '유동인구 데이터를 불러오지 못했습니다.'
            : '이 위치는 유동인구 분석에 필요한 자료가 없습니다.'}
        </p>
      </div>
    );
  }

  return (
    <div className="fp-root flex w-full flex-col items-start">
      <TypeHeaderCard data={data} />
      <CoreStat data={data} />
      <RadiusProfileChart data={data} />
      <AgeDistribution data={data} />
      <TrendChart data={data} />
      <TradeAreaList data={data} />

      {shouldShowWarnings(data.status) && data.warnings.length > 0 && (
        <ul className="fp-warnings">
          {data.warnings.map((warning) => (
            <li key={warning}>※ {warning}</li>
          ))}
        </ul>
      )}

      <p className="fp-source">
        {data.sources.map((source, i) => (
          <span key={source.name}>
            자료출처: {source.name} · {source.license}
            {i < data.sources.length - 1 && <br />}
          </span>
        ))}
      </p>

      {/*
        구간별로 달라지는 값은 전부 이 블록 하나에서만 관리한다(위 마크업에는
        크기 관련 Tailwind 클래스를 달지 않는다). Badge/DivergingBar만 공용
        컴포넌트라 fluid() inline style(Badge) 또는 자체 <style jsx global>
        (DivergingBar)을 각각 병행한다 — CompetitorAnalysisSection.tsx와
        동일 원칙.

        레이아웃 구조가 바뀌는 지점(연령 분포: 도넛+지수 세로 ↔ 가로)만
        640px에서 flex-direction을 교체하고, 나머지는 375px→1440px 한
        구간을 clamp() 하나로 보간한다.
      */}
      <style jsx global>{`
        .fp-root {
          gap: clamp(16px, calc(16px + (100vw - 375px) * 0.007512), 24px);
          padding-inline: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.015023),
            32px
          );
          padding-block: clamp(
            20px,
            calc(20px + (100vw - 375px) * 0.011268),
            32px
          );
        }
        .fp-root-empty {
          align-items: center;
          justify-content: center;
          min-height: 160px;
        }

        .fp-card-head {
          padding-inline: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.00939),
            24px
          );
          padding-block: clamp(
            12px,
            calc(12px + (100vw - 375px) * 0.005634),
            18px
          );
          gap: 2px;
        }
        .fp-card-title {
          font-size: clamp(15px, calc(15px + (100vw - 375px) * 0.003756), 19px);
        }
        .fp-card-desc {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          line-height: 1.5;
        }
        .fp-card-body {
          padding-inline: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.00939),
            24px
          );
          padding-block: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.007512),
            20px
          );
          gap: clamp(6px, calc(6px + (100vw - 375px) * 0.001878), 10px);
        }

        .fp-empty-note {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px);
          color: var(--color-gray-500);
          padding-block: 8px;
          line-height: 1.6;
        }

        /* ---- 1. 유형 카드 ---- */
        .fp-type-card {
          display: flex;
          flex-direction: column;
          gap: clamp(10px, calc(10px + (100vw - 375px) * 0.005634), 16px);
          padding: clamp(16px, calc(16px + (100vw - 375px) * 0.00939), 26px);
        }
        .fp-type-head {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .fp-type-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .fp-type-reasons {
          display: flex;
          flex-direction: column;
          gap: 4px;
          width: 100%;
          list-style: disc;
          padding-left: 18px;
          color: var(--color-gray-600);
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px);
          line-height: 1.6;
        }

        /* ---- 2. 핵심 stat ---- */
        .fp-core-stats {
          display: grid;
          grid-template-columns: 1fr 1fr;
          width: 100%;
          gap: clamp(12px, calc(12px + (100vw - 375px) * 0.005634), 16px);
        }
        .fp-core-value {
          font-weight: 700;
          font-size: clamp(22px, calc(22px + (100vw - 375px) * 0.007512), 34px);
          line-height: 1.3;
        }
        .fp-core-unit {
          font-size: clamp(13px, calc(13px + (100vw - 375px) * 0.001878), 15px);
          color: var(--color-gray-400);
          margin-left: 4px;
        }
        .fp-core-prefix {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px);
          color: var(--color-gray-500);
        }

        /* ---- 3. 연령대별 분포 ---- */
        .fp-age-wrap {
          display: flex;
          flex-direction: column;
          width: 100%;
          gap: clamp(14px, calc(14px + (100vw - 375px) * 0.007512), 22px);
        }
        .fp-age-donut {
          display: flex;
          flex-direction: column;
          width: 100%;
          gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 14px);
        }
        .fp-donut-chart {
          width: 100%;
          height: clamp(140px, calc(140px + (100vw - 375px) * 0.02817), 168px);
        }
        .fp-donut-legend {
          display: grid;
          grid-template-columns: 1fr;
          gap: 6px;
          width: 100%;
        }
        .fp-donut-legend-row {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .fp-donut-swatch {
          width: 10px;
          height: 10px;
          border-radius: 3px;
          flex: 0 0 auto;
        }
        .fp-donut-legend-name {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
          flex: 1 1 auto;
          min-width: 0;
        }
        .fp-donut-legend-value {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
          flex: 0 0 auto;
        }
        .fp-age-index {
          display: flex;
          flex-direction: column;
          width: 100%;
          gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 12px);
        }
        .fp-age-index-label {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
        }
        @media (min-width: 640px) {
          .fp-age-wrap {
            flex-direction: row;
            align-items: flex-start;
          }
          .fp-age-donut {
            flex: 0 0 auto;
            width: clamp(200px, calc(200px + (100vw - 640px) * 0.05), 240px);
          }
          .fp-age-index {
            flex: 1 1 auto;
          }
        }

        /* ---- 추세 / 반경별 차트 (공통 스타일) ---- */
        .fp-chart-wrap {
          width: 100%;
        }
        /*
          showPointLabels가 찍는 라벨(.area-chart-point-label*)의 크기/색/반응형
          숨김 규칙은 AreaChart.tsx 자신이 <style jsx global>로 갖고 있다(그
          컴포넌트가 렌더링하는 SVG <text> 클래스라, 라벨을 실제로 그리는
          곳이 스타일도 함께 소유해야 다른 파일에서 재사용할 때도 별도
          복제 없이 그대로 적용된다). 여기서는 정의하지 않는다.
        */
        .fp-trend-caption,
        .fp-radius-caption {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          color: var(--color-gray-600);
          padding-top: 4px;
        }
        .fp-radius-method {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-400);
        }

        /* ---- 6. 집계 상권 목록 ---- */
        .fp-trade-area-list {
          display: flex;
          flex-direction: column;
          width: 100%;
          gap: 2px;
        }
        .fp-trade-area-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          padding-block: clamp(
            6px,
            calc(6px + (100vw - 375px) * 0.002817),
            9px
          );
          border-bottom: 1px solid ${colors.neutral.background};
        }
        .fp-trade-area-row:last-child {
          border-bottom: none;
        }
        .fp-trade-area-name {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
        }

        .fp-warnings {
          display: flex;
          flex-direction: column;
          gap: 2px;
          width: 100%;
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
          padding-top: 4px;
        }

        .fp-source {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-400);
          line-height: 1.6;
        }
      `}</style>
    </div>
  );
}
