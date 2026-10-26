'use client';

import { pretendard } from '@/styles/fonts';
import { Footprints, BarChart3, Users, Activity } from 'lucide-react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import RevealBarChart from '@/components/charts/RevealBarChart';
import PopulationBarChart from '@/components/charts/PopulationBarChart';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { colors } from '@/styles/tokens';
import {
  mockReportData,
  type AgentStatus,
  type FloatingPopulationData,
  type ReliabilityLevel,
} from '@/lib/mockData/report';

const outfit = pretendard;

const dmMono = pretendard;

const fluid = (min: number, max: number) =>
  `clamp(${min}px, calc(${min}px + (100vw - 375px) * ${(
    (max - min) /
    1065
  ).toFixed(6)}), ${max}px)`;

// 글씨 크기 전용 — fluid() 값에 글씨 배율(--font-scale)을 곱한다. fluid()는
// 간격·폭에도 쓰이므로 함수 자체에는 배율을 넣지 않는다.
const fluidFont = (min: number, max: number) =>
  `calc(${fluid(min, max)} * var(--font-scale))`;

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
            fontSize: fluidFont(16, 22),
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
              fontSize: fluidFont(10, 12),
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
              fontSize: fluidFont(10, 12),
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
      <SectionCard
        title="하루 평균 유동인구"
        description={`분석 반경 ${data.radius_m}m · ${Array.from(new Set(data.sources.map((source) => source.period))).join(' · ') || '집계 기간 미제공'}. 주변 상권의 추정 통행량이며 상가 앞 통행량이나 중복을 제외한 방문자 수가 아닙니다.`}
      >
        <p className={`fp-core-value ${dmMono.className}`}>
          <span style={{ color: colors.brand.dark }}>
            {Math.round(data.population.daily_avg).toLocaleString('ko-KR')}
          </span>
          <span className="fp-core-unit">명/일</span>
        </p>
      </SectionCard>
      <SectionCard
        title="상권 규모"
        description="서울 상권과 비교한 규모 순위입니다. 상위 비율이 작을수록 규모가 크며, 예상 매출을 뜻하지 않습니다."
      >
        <p className="fp-core-prefix">서울 상권 상위</p>
        <p className={`fp-core-value ${dmMono.className}`}>
          <span style={{ color: colors.brand.dark }}>{topPercent}</span>
          <span className="fp-core-unit">%</span>
        </p>
      </SectionCard>
    </div>
  );
}

// 도넛, 범례, 구성 비율 막대가 동일한 연령대 팔레트를 공유합니다.
const AGE_COLORS = [
  '#1947B3',
  '#254591',
  '#F0AE6A',
  '#97ACDC',
  '#607AB8',
  '#F6CCA8',
];

/** 연령대 구성 표(도넛 + 구성 비율 + 서울 평균 대비). 카드형·읽기형이 함께 쓴다. */
function AgeComparison({ data }: { data: FloatingPopulationData }) {
  const ageKeys = Object.keys(data.population.age_share);
  const slices = ageKeys.map((key, i) => ({
    name: formatAgeLabel(key),
    value: data.population.age_share[key],
    color: AGE_COLORS[i % AGE_COLORS.length],
  }));
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  return (
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
        <p className="age-composition-note">이 지역의 연령 구성</p>
      </div>
      <div className="age-comparison-table">
        <div className="age-table-head">
          <span>연령대</span>
          <span>구성 비율</span>
          <span>
            서울 평균 대비 <small>1.0배 기준</small>
          </span>
        </div>
        {slices.map((slice, i) => {
          const index = data.benchmark.age_index[ageKeys[i]] ?? null;
          const maxIndex = Math.max(
            2,
            ...Object.values(data.benchmark.age_index).filter(
              (v): v is number => typeof v === 'number'
            )
          );
          const baseline = 100 / maxIndex;
          const endpoint =
            index === null ? baseline : Math.min(100, (index / maxIndex) * 100);
          const share = total > 0 ? (slice.value / total) * 100 : 0;
          const dominant =
            slice.value === Math.max(...slices.map((s) => s.value));
          return (
            <div
              className={`age-table-row ${dominant ? 'dominant' : ''}`}
              key={slice.name}
            >
              <span className="age-row-label">
                <i style={{ backgroundColor: slice.color }} />
                {slice.name}
              </span>
              <div className="age-share">
                <strong>
                  {share.toFixed(1)}
                  <small>%</small>
                </strong>
                <div aria-hidden="true">
                  <span
                    style={{
                      width: `${share}%`,
                      backgroundColor: slice.color,
                    }}
                  />
                </div>
              </div>
              <div className="age-index-cell">
                <div className="age-index-track" aria-hidden="true">
                  <i style={{ left: `${baseline}%` }} />
                  {index !== null && (
                    <span
                      className={index >= 1 ? 'above' : 'below'}
                      style={{
                        left: `${Math.min(baseline, endpoint)}%`,
                        width: `${Math.abs(endpoint - baseline)}%`,
                      }}
                    />
                  )}
                </div>
                <strong>
                  {index === null ? '자료 없음' : `${index.toFixed(2)}배`}
                </strong>
              </div>
            </div>
          );
        })}
        <p className="age-table-note">
          1.0배보다 높으면 서울 평균보다 많고, 낮으면 적습니다.
        </p>
      </div>
    </div>
  );
}

/** 4. 연령대별 분포 */
function AgeDistribution({ data }: { data: FloatingPopulationData }) {
  return (
    <SectionCard
      title="연령대별 분포"
      description="이 반경 유동인구의 연령대 구성과, 서울 평균 대비 각 연령대가 얼마나 많은지를 함께 보여줍니다."
    >
      <AgeComparison data={data} />
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
        <RevealBarChart data={points} label="분기별 하루 평균 유동인구" />
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
        <RevealBarChart data={points} label="반경별 하루 평균 유동인구" />
      </div>
      <p className="fp-radius-caption">
        50~100m 구간은 표본이 적어 추정 성격이 강합니다.
      </p>
      <p className="fp-radius-method">{data.radius_profile.method}</p>
    </SectionCard>
  );
}

/** 6. 집계 상권 목록 */
function TradeAreaList({
  data,
  plain = false,
}: {
  data: FloatingPopulationData;
  plain?: boolean;
}) {
  if (!data.trade_areas) {
    return (
      <SelectionReasonNote
        data={data}
        droppedKey="trade_areas"
        fallbackTitle="집계 상권 목록"
      />
    );
  }

  const list = (
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
                fontSize: fluidFont(9, 11),
              }}
            >
              {area.kind}
            </Badge>
          )}
        </li>
      ))}
    </ul>
  );

  if (plain) {
    return (
      <div className="mt-4 border-t border-gray-200 pt-4">
        <p className="mb-3 text-sm leading-6 text-gray-500">
          분석에 사용한 상권 구역입니다. 동네 개수를 의미하지 않습니다.
        </p>
        {list}
      </div>
    );
  }

  return (
    <SectionCard
      title="집계 상권 목록"
      description="이 지역을 나눈 조각들입니다. 동네 개수가 아닙니다."
    >
      {list}
    </SectionCard>
  );
}

/**
 * 리포트용 읽기형 구성 — 카드를 쌓는 대신 결론 → 핵심 숫자 → 근거(질문별 행)
 * 순서로 위에서 아래로 읽히게 한다. 스타일은 app/report/report.css의 .story 블록.
 */
function PopulationStory({ data }: { data: FloatingPopulationData }) {
  const periods = [...new Set(data.sources.map((source) => source.period))];
  const ageEntries = Object.entries(data.population.age_share);
  const ageTotal = ageEntries.reduce((sum, [, value]) => sum + value, 0);
  const topAge = ageEntries.reduce<[string, number] | null>(
    (best, entry) => (!best || entry[1] > best[1] ? entry : best),
    null
  );

  return (
    <div className="story">
      <header className="story-lead">
        <h3>
          이 주변은 <em>{data.type.label}</em> 상권이에요
        </h3>
        <p className="story-meta">
          신뢰도 {RELIABILITY_LABEL[data.reliability.level]} ·{' '}
          {data.reliability.trade_area_count}곳 중{' '}
          {data.reliability.covered_trade_areas}곳 자료 확보
        </p>
        <ul className="story-insights">
          {data.type.reasons.map((reason) => (
            <li key={reason}>
              {reason
                .split(/(\d+(?:\.\d+)?(?:%|배))/g)
                .map((part, i) =>
                  /^(\d+(?:\.\d+)?(?:%|배))$/.test(part) ? (
                    <strong key={i}>{part}</strong>
                  ) : (
                    part
                  )
                )}
            </li>
          ))}
        </ul>
      </header>

      <dl className="story-stats">
        <div>
          <dt>
            <span className="story-stat-icon" aria-hidden="true">
              <Footprints size={18} strokeWidth={2} />
            </span>
            하루 평균 유동인구
          </dt>
          <dd>
            {Math.round(data.population.daily_avg).toLocaleString('ko-KR')}
            <small>명/일</small>
          </dd>
          <p>
            반경 {data.radius_m}m · {periods.join(' · ') || '기간 미제공'}
          </p>
        </div>
        <div>
          <dt>
            <span className="story-stat-icon" aria-hidden="true">
              <BarChart3 size={18} strokeWidth={2} />
            </span>
            서울 상권 규모
          </dt>
          <dd>
            <small>상위</small>
            {100 - data.benchmark.scale_percentile}
            <small>%</small>
          </dd>
          <p>작을수록 큰 상권 · 매출 예측 아님</p>
        </div>
        {topAge && (
          <div>
            <dt>
              <span className="story-stat-icon" aria-hidden="true">
                <Users size={18} strokeWidth={2} />
              </span>
              가장 많은 연령대
            </dt>
            <dd>
              {formatAgeLabel(topAge[0])}
              <small>
                {ageTotal > 0
                  ? `${((topAge[1] / ageTotal) * 100).toFixed(0)}%`
                  : ''}
              </small>
            </dd>
            <p>이 반경 유동인구 기준</p>
          </div>
        )}
        {data.trend && data.trend.qoq_change !== null && (
          <div>
            <dt>
              <span className="story-stat-icon" aria-hidden="true">
                <Activity size={18} strokeWidth={2} />
              </span>
              전분기 대비
            </dt>
            <dd>
              {data.trend.qoq_change > 0 ? '+' : ''}
              {data.trend.qoq_change}
              <small>%</small>
            </dd>
            <p>{data.trend.direction}</p>
          </div>
        )}
      </dl>

      <AgeStory data={data} />

      {data.radius_profile && <RadiusStory data={data} />}
      {data.trend && <TrendStory data={data} />}
    </div>
  );
}

/** 눈금 끝값을 0.25배 단위로 맞춘 1.0배 중심 범위(예: 0.25 ~ 1.75배). */
function indexRange(values: number[]) {
  const spread = Math.max(0.25, ...values.map((v) => Math.abs(v - 1)));
  const half = Math.ceil(spread / 0.25) * 0.25;
  return { min: Math.max(0, 1 - half), max: 1 + half };
}

function formatIndex(value: number) {
  return `${value.toFixed(2)}배`;
}

/**
 * 연령대 구성 — 서로 기준이 다른 두 지표를 나란히 보여준다.
 * - 구성비: 이 반경 유동인구 중 그 연령대 비율(합 100%)
 * - 서울 평균 대비: 이 반경 구성비 ÷ 서울 전체 상권 평균 구성비
 *   (backend floating_population/baseline.py index(), AGE_SHARE_AVG)
 * 행 강조는 쓰지 않고, 각 지표의 1위에만 이유를 적은 태그를 붙인다.
 */
function AgeStory({ data }: { data: FloatingPopulationData }) {
  const keys = Object.keys(data.population.age_share);
  const total = keys.reduce(
    (sum, key) => sum + data.population.age_share[key],
    0
  );
  const rows = keys.map((key) => ({
    key,
    label: formatAgeLabel(key),
    share: total > 0 ? (data.population.age_share[key] / total) * 100 : 0,
    index: data.benchmark.age_index[key] ?? null,
  }));
  if (rows.length === 0) return null;

  const topShare = rows.reduce((best, row) =>
    row.share > best.share ? row : best
  );
  const indexed = rows.filter(
    (row): row is typeof row & { index: number } => row.index !== null
  );
  const topIndex = indexed.reduce<(typeof indexed)[number] | null>(
    (best, row) => (!best || row.index > best.index ? row : best),
    null
  );
  const range = indexRange(indexed.map((row) => row.index));
  const span = range.max - range.min;
  const toPercent = (value: number) =>
    ((Math.min(range.max, Math.max(range.min, value)) - range.min) / span) *
    100;
  const shareCeiling = Math.max(10, Math.ceil(topShare.share / 10) * 10);
  const periods = [...new Set(data.sources.map((source) => source.period))];

  return (
    <section className="story-row story-row-stack">
      <div className="story-row-head">
        <p className="story-question">누가 오가나요?</p>
        <h4>
          연령대 구성
          <span className="story-scope">
            반경 {data.radius_m}m
            {periods.length > 0 && ` · ${periods.join(' · ')}`}
          </span>
        </h4>
      </div>

      <div className="age-summary">
        <p>
          <span className="age-summary-tag">구성비</span>
          <strong>{topShare.label}</strong> 비중이 가장 높아요
          <b>{topShare.share.toFixed(1)}%</b>
        </p>
        {topIndex && (
          <p>
            <span className="age-summary-tag age-summary-tag-index">
              서울 평균 대비
            </span>
            <strong>{topIndex.label}</strong> 비중이 가장 두드러져요
            <b>{formatIndex(topIndex.index)}</b>
          </p>
        )}
      </div>

      <div
        className="age-grid"
        role="table"
        aria-label="연령대별 구성비와 서울 평균 대비 배수"
      >
        <div className="age-grid-head" role="row">
          <span role="columnheader">연령대</span>
          <span role="columnheader">
            구성비
            <small>유동인구 중 비율</small>
          </span>
          <span role="columnheader">
            서울 평균 대비
            <small>구성비 배수 · 1.0배 = 서울 평균</small>
          </span>
        </div>
        <div className="age-grid-axis" aria-hidden="true">
          <span />
          <span className="age-axis-share">
            <i>0%</i>
            <i>{shareCeiling}%</i>
          </span>
          <span className="age-axis-index">
            <i style={{ left: '0%' }}>{range.min.toFixed(2)}</i>
            <i style={{ left: `${toPercent(1)}%` }}>1.0배</i>
            <i style={{ left: '100%' }}>{range.max.toFixed(2)}</i>
          </span>
        </div>
        {rows.map((row) => {
          const isTopShare = row === topShare;
          const isTopIndex = row === topIndex;
          const center = toPercent(1);
          const end = row.index === null ? center : toPercent(row.index);
          return (
            <div className="age-grid-row" role="row" key={row.key}>
              <span className="age-cell-label" role="rowheader">
                {row.label}
                {/* 좁은 화면에서는 강조 이유를 연령대 옆에 모아 둔다(값 칸 폭을 고정). */}
                {isTopShare && (
                  <b className="age-flag age-flag-share age-flag-inline">
                    구성비 1위
                  </b>
                )}
                {isTopIndex && (
                  <b className="age-flag age-flag-inline">평균 대비 최고</b>
                )}
              </span>
              <div className="age-cell-share" role="cell">
                <em className="age-cell-caption">구성비</em>
                <div className="age-share-track" aria-hidden="true">
                  <span
                    className={isTopShare ? 'is-top' : ''}
                    style={{ width: `${(row.share / shareCeiling) * 100}%` }}
                  />
                </div>
                <span className="age-value">
                  <strong>{row.share.toFixed(1)}%</strong>
                  {isTopShare && (
                    <b className="age-flag age-flag-share">구성비 1위</b>
                  )}
                </span>
              </div>
              <div className="age-cell-index" role="cell">
                <em className="age-cell-caption">서울 평균 대비</em>
                <div className="age-index-scale" aria-hidden="true">
                  <i style={{ left: `${center}%` }} />
                  {row.index !== null && (
                    <span
                      className={row.index >= 1 ? 'is-above' : 'is-below'}
                      style={{
                        left: `${Math.min(center, end)}%`,
                        width: `${Math.abs(end - center)}%`,
                      }}
                    />
                  )}
                </div>
                <span className="age-value">
                  <strong>
                    {row.index === null ? '자료 없음' : formatIndex(row.index)}
                  </strong>
                  {isTopIndex && <b className="age-flag">평균 대비 최고</b>}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <ul className="story-notes">
        <li>
          <strong>구성비</strong>: 이 반경 유동인구 중 그 연령대가 차지하는
          비율이에요(합계 100%).
        </li>
        <li>
          <strong>서울 평균 대비</strong>: 이 반경의 연령대 구성비 ÷ 서울 전체
          상권의 평균 구성비예요. 사람 수가 아니라 <strong>비중</strong>을
          비교한 값이에요.
          {topIndex &&
            ` 예를 들어 ${topIndex.label} ${formatIndex(topIndex.index)}는 “${topIndex.label}가 그만큼 많이 지나간다”가 아니라 “${topIndex.label} 비중이 서울 평균의 ${formatIndex(topIndex.index)}”라는 뜻이에요.`}
        </li>
        <li>
          길을 지나는 유동인구(통행량) 기준이라 실제 매장 방문객 수와는 달라요.
        </li>
      </ul>
    </section>
  );
}

/** 50m·100m처럼 작은 반경은 걸친 상권이 적어 추정 성격이 강하다(각주 * 로 연결). */
const SMALL_RADIUS_LIMIT_M = 100;

/** 반경별 인구 — 값은 그 반경 안 전체(누적)다. backend metrics._radius_profile 참고. */
function RadiusStory({ data }: { data: FloatingPopulationData }) {
  const points = data.radius_profile?.points ?? [];
  if (points.length === 0) return null;
  const nearest = points[0];
  const widest = points[points.length - 1];
  const small = points
    .filter((point) => point.radius_m <= SMALL_RADIUS_LIMIT_M)
    .map((point) => `${point.radius_m}m`);

  return (
    <section className="story-row story-row-stack">
      <div className="story-row-head">
        <p className="story-question">어디까지 퍼져 있나요?</p>
        <h4>반경별 인구</h4>
      </div>
      <div className="story-summary">
        <p className="story-summary-main">
          반경 {widest.radius_m}m 안 하루 평균{' '}
          <strong>
            {Math.round(widest.daily_avg).toLocaleString('ko-KR')}
          </strong>
          명
        </p>
        <p className="story-summary-sub">
          가장 가까운 반경 {nearest.radius_m}m 안에는{' '}
          {Math.round(nearest.daily_avg).toLocaleString('ko-KR')}명이에요.
        </p>
      </div>
      <PopulationBarChart
        data={points.map((point) => ({
          label: `${point.radius_m}m 이내`,
          value: Math.round(point.daily_avg),
          footnote: point.radius_m <= SMALL_RADIUS_LIMIT_M,
        }))}
        label="반경 안 하루 평균 유동인구(누적)"
        unit="하루 평균 유동인구(명) · 반경 안 누적"
      />
      <ul className="story-notes">
        <li>
          각 막대는 그 반경 <strong>안 전체를 합친 값</strong>이에요. 거리
          구간(예: 100~200m)별 인구가 아니에요.
        </li>
        {small.length > 0 && (
          <li>
            <span className="story-notes-mark">*</span> 반경 {small.join('·')}{' '}
            안은 표본이 적어 추정 성격이 강해요.
          </li>
        )}
        {data.radius_profile?.method && (
          <li>산정 기준: {data.radius_profile.method}</li>
        )}
      </ul>
    </section>
  );
}

function formatChange(change: number) {
  if (change === 0) return '0%';
  return `${change > 0 ? '▲' : '▼'} ${Math.abs(change)}%`;
}

/** 분기별 추세 — 최신 분기만 강조하고, 직전 분기 대비 변화율을 최신 값 옆에 둔다. */
function TrendStory({ data }: { data: FloatingPopulationData }) {
  const trend = data.trend;
  if (!trend || trend.quarters.length === 0) return null;
  const latest = trend.quarters[trend.quarters.length - 1];
  const change = trend.qoq_change;

  return (
    <section className="story-row story-row-stack">
      <div className="story-row-head">
        <p className="story-question">늘고 있나요?</p>
        <h4>분기별 추세</h4>
      </div>
      <div className="story-summary">
        <p className="story-summary-main">
          {latest.period} 하루 평균{' '}
          <strong>
            {Math.round(latest.daily_avg).toLocaleString('ko-KR')}
          </strong>
          명
          {change !== null && (
            <span className="story-change">
              직전 분기 대비 {formatChange(change)}
            </span>
          )}
          {trend.direction !== '판단 불가' && (
            <span className="story-direction">{trend.direction}</span>
          )}
        </p>
        {trend.direction === '보합' && (
          <p className="story-summary-sub">
            변화율이 ±5% 이내면 ‘보합’으로 봐요. 전년 같은 분기 자료가 있으면
            그것과, 없으면 직전 분기와 비교해요.
          </p>
        )}
      </div>
      <PopulationBarChart
        data={trend.quarters.map((quarter) => ({
          label: quarter.period,
          value: Math.round(quarter.daily_avg),
        }))}
        label="분기별 하루 평균 유동인구"
        unit="하루 평균 유동인구(명)"
        highlightIndex={trend.quarters.length - 1}
        highlightTag="최신 분기"
        annotation={change !== null ? formatChange(change) : undefined}
      />
    </section>
  );
}

export default function FloatingPopulationSection({
  data = mockReportData.floatingPopulation as FloatingPopulationData,
  compactReference = false,
  reportLayout = false,
}: {
  data?: FloatingPopulationData;
  compactReference?: boolean;
  reportLayout?: boolean;
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
    <div
      className={`fp-root flex w-full flex-col items-start ${reportLayout ? 'fp-root-story' : ''}`}
    >
      {reportLayout ? (
        <PopulationStory data={data} />
      ) : (
        <>
          <TypeHeaderCard data={data} />
          <CoreStat data={data} />
          <RadiusProfileChart data={data} />
          <AgeDistribution data={data} />
          <TrendChart data={data} />
        </>
      )}
      {compactReference ? (
        <details className="report-raw-reference w-full rounded-xl border border-gray-200 bg-white px-5 py-4">
          <summary className="cursor-pointer text-base font-semibold text-gray-700">
            참고자료 · 집계 지역 확인하기
            {data.trade_areas ? ` (${data.trade_areas.length}곳)` : ''}
          </summary>
          <TradeAreaList data={data} plain />
        </details>
      ) : (
        <TradeAreaList data={data} />
      )}

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
          font-size: calc(
            clamp(15px, calc(15px + (100vw - 375px) * 0.003756), 19px) *
              var(--font-scale)
          );
        }
        .fp-card-desc {
          font-size: calc(
            clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(22px, calc(22px + (100vw - 375px) * 0.007512), 34px) *
              var(--font-scale)
          );
          line-height: 1.3;
        }
        .fp-core-unit {
          font-size: calc(
            clamp(13px, calc(13px + (100vw - 375px) * 0.001878), 15px) *
              var(--font-scale)
          );
          color: var(--color-gray-400);
          margin-left: 4px;
        }
        .fp-core-prefix {
          font-size: calc(
            clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px) *
              var(--font-scale)
          );
          color: ${colors.neutral.black};
          flex: 1 1 auto;
          min-width: 0;
        }
        .fp-donut-legend-value {
          font-size: calc(
            clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px) *
              var(--font-scale)
          );
          color: var(--color-gray-600);
          padding-top: 4px;
        }
        .fp-radius-method {
          font-size: calc(
            clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px) *
              var(--font-scale)
          );
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
          font-size: calc(
            clamp(12px, calc(12px + (100vw - 375px) * 0.002817), 14px) *
              var(--font-scale)
          );
          color: ${colors.neutral.black};
        }

        .fp-warnings {
          display: flex;
          flex-direction: column;
          gap: 2px;
          width: 100%;
          font-size: calc(
            clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px) *
              var(--font-scale)
          );
          color: var(--color-gray-500);
          padding-top: 4px;
        }

        .fp-source {
          font-size: calc(
            clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px) *
              var(--font-scale)
          );
          color: var(--color-gray-400);
          line-height: 1.6;
        }
      `}</style>
    </div>
  );
}
