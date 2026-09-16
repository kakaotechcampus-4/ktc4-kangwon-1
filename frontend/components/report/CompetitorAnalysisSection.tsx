'use client';

import { useEffect } from 'react';
import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import AreaChart from '@/components/charts/AreaChart';
import DivergingBar from '@/components/report/DivergingBar';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { colors } from '@/styles/tokens';
import {
  mockReportData,
  RECOMMENDED_NAME_TO_MIDDLE_CODE,
  type AgentStatus,
  type CommercialAreaData,
  type CommercialAreaMiddleCategory,
  type CommercialAreaSpecializationRank,
  type RecommendedIndustry,
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
 * status에 따라 전체 섹션을 그릴지, 안내 문구만 보여줄지 결정한다.
 * no_data/error는 백엔드 스키마상 data가 비어 있는 상태를 뜻하므로
 * (AgentAnalysis.check_status) A/B 섹션을 아예 그리지 않는다.
 * 375/768/1024/1440 스크린샷은 'partial'(정상 데이터 + 각주) 시나리오만
 * 담고 있고, no_data/error 분기는 아래 로직을 코드 리뷰로 직접 확인했다
 * (한 줄짜리 상태 비교라 별도 렌더 시나리오 없이도 충분히 검증 가능하다고
 * 판단했다).
 */
export function getSectionVisibility(
  status: AgentStatus
): 'visible' | 'hidden' {
  return status === 'no_data' || status === 'error' ? 'hidden' : 'visible';
}

export function shouldShowWarnings(status: AgentStatus): boolean {
  return status === 'partial';
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
      className="ca-card w-full"
      style={{
        padding: 0,
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow:
          '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
      }}
    >
      <div
        className="ca-card-head flex w-full flex-col items-start"
        style={{ borderBottom: `1px solid ${colors.neutral.border}` }}
      >
        <p
          className={`ca-card-title ${outfit.className} font-bold`}
          style={{ color: colors.neutral.black }}
        >
          {title}
        </p>
        {description && (
          <p className="ca-card-desc text-gray-500">{description}</p>
        )}
      </div>
      <div className="ca-card-body flex w-full flex-col items-start">
        {children}
      </div>
    </Card>
  );
}

/** A-1. 반경별 점포 수 증가 곡선 */
function RadiusGrowthChart({ data }: { data: CommercialAreaData }) {
  const points = data.byRadius.map((slice) => ({
    label: `${slice.radiusM}m`,
    value: slice.storeTotal,
  }));

  return (
    <SectionCard
      title="반경별 점포 수"
      description="반경이 넓어질수록 상권 안 점포 수가 어떻게 늘어나는지 보여줍니다."
    >
      <div className="ca-chart-wrap">
        <AreaChart
          data={points}
          height={200}
          valueSuffix="개"
          showPointLabels
        />
      </div>
    </SectionCard>
  );
}

// 고정 순서 팔레트. 순환시키지 않고(9번째 이상은 전부 "기타"로 묶는다),
// 항상 이 순서대로 색을 배정해 같은 업종이 항상 같은 색으로 보이게 한다.
const CATEGORY_COLORS = [
  colors.brand.primary,
  colors.brand.dark,
  colors.accent.orange,
  `${colors.brand.primary}99`,
  `${colors.brand.dark}99`,
  `${colors.accent.orange}99`,
  'var(--color-gray-400)',
  'var(--color-gray-300)',
];
const OTHER_COLOR = 'var(--color-gray-500)';

type DonutSlice = { name: string; value: number; color: string };

function Donut({
  slices,
  height = 168,
}: {
  slices: DonutSlice[];
  height?: number;
}) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  return (
    <div className="ca-donut-wrap">
      <div className="ca-donut-chart" style={{ height }}>
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
      <div className="ca-donut-legend">
        {slices.map((slice) => (
          <div key={slice.name} className="ca-donut-legend-row">
            <span
              className="ca-donut-swatch"
              style={{ backgroundColor: slice.color }}
            />
            <span className="ca-donut-legend-name">{slice.name}</span>
            <span className={`ca-donut-legend-value ${dmMono.className}`}>
              {slice.value.toLocaleString('ko-KR')}개 ·{' '}
              {((slice.value / total) * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** A-2. 대분류 업종 구성 */
function MajorCategoryDonut({ data }: { data: CommercialAreaData }) {
  const sorted = [...data.byMajor]
    .filter((m) => m.count > 0)
    .sort((a, b) => b.count - a.count);
  const top = sorted.slice(0, 8);
  const rest = sorted.slice(8);
  const restTotal = rest.reduce((sum, m) => sum + m.count, 0);

  const slices: DonutSlice[] = top.map((m, i) => ({
    name: m.name,
    value: m.count,
    color: CATEGORY_COLORS[i],
  }));
  if (restTotal > 0) {
    slices.push({ name: '기타', value: restTotal, color: OTHER_COLOR });
  }

  return (
    <SectionCard
      title="대분류 업종 구성"
      description={`반경 ${data.radiusM.toLocaleString('ko-KR')}m 안 점포를 대분류 기준으로 나눈 비중입니다.`}
    >
      <Donut slices={slices} />
    </SectionCard>
  );
}

/** A-3. 업종 다양성 */
function DiversityStat({ data }: { data: CommercialAreaData }) {
  const currentSlice = data.byRadius.find((r) => r.radiusM === data.radiusM);
  const observed = currentSlice?.categoryCount ?? 0;
  const effective = data.diversity.effectiveCategories;

  return (
    <SectionCard
      title="업종 다양성"
      description="업종 쏠림을 고려했을 때, 실질적으로 몇 종류의 업종이 고르게 있는지를 뜻합니다."
    >
      <div className="ca-diversity-stat">
        <p className={`ca-diversity-value ${dmMono.className}`}>
          <span style={{ color: colors.brand.dark }}>{effective}</span>
          <span className="ca-diversity-unit">종</span>
        </p>
        <p className="ca-diversity-caption">
          관측된 {observed}종 업종 중 실질 다양성 {effective}종
        </p>
      </div>
    </SectionCard>
  );
}

/** A-4. 프랜차이즈 vs 개인사업자 */
function FranchiseDonut({ data }: { data: CommercialAreaData }) {
  if (!data.franchise) {
    return null;
  }

  const franchise = data.franchise;
  const independentCount = Math.max(0, data.storeTotal - franchise.count);
  const slices: DonutSlice[] = [
    { name: '프랜차이즈', value: franchise.count, color: colors.brand.dark },
    {
      name: '개인사업자(추정)',
      value: independentCount,
      color: 'var(--color-gray-300)',
    },
  ];

  // '높음'/'보통'/'낮음'은 명사형 라벨이라 뒤에 그대로 "습니다"를 붙이면
  // "낮음습니다"처럼 어법이 깨진다. 서술어 전체를 미리 활용형으로 만들어 둔다.
  const confidencePredicate =
    franchise.confidence === 'high'
      ? '높습니다'
      : franchise.confidence === 'medium'
        ? '보통입니다'
        : '낮습니다';

  return (
    <SectionCard
      title="프랜차이즈 vs 개인사업자"
      description="전체 점포 중 프랜차이즈 브랜드로 추정되는 비율입니다."
    >
      <Donut slices={slices} />
      <p className="ca-franchise-caveat">
        상호명을 브랜드명과 대조하는 방식으로 판정해 신뢰도가{' '}
        <strong>{confidencePredicate}</strong>. 실제 가맹 여부와 다를 수
        있습니다.
      </p>
    </SectionCard>
  );
}

/** A-5. 500m 반경 상위 업종 TOP10 */
function TopByCountBars({ data }: { data: CommercialAreaData }) {
  const slice = data.byRadius.find((r) => r.radiusM === 500);
  if (!slice || slice.topByCount.length === 0) {
    return null;
  }

  const max = Math.max(...slice.topByCount.map((c) => c.count));

  return (
    <SectionCard
      title="500m 반경 상위 업종"
      description="반경 500m 안에서 점포 수가 가장 많은 업종 10개입니다."
    >
      {slice.topByCount.map((item) => (
        <div key={item.code} className="ca-bar-row">
          <span className="ca-bar-label">{item.name}</span>
          <div className="ca-bar-track">
            <div
              className="ca-bar-fill"
              style={{
                width: `${(item.count / max) * 100}%`,
                backgroundColor: colors.brand.primary,
              }}
            />
          </div>
          <span className="ca-bar-note">{item.note}</span>
        </div>
      ))}
    </SectionCard>
  );
}

/** A-6. 자치구 대비 특화 업종 TOP10 */
function DistrictSpecializationBars({ data }: { data: CommercialAreaData }) {
  if (data.districtSpecialization.length === 0) {
    return (
      <SectionCard title="자치구 대비 특화 업종">
        <p className="ca-empty-note">자치구 비교 자료 없음</p>
      </SectionCard>
    );
  }

  const values = data.districtSpecialization.map(
    (item: CommercialAreaSpecializationRank) => item.timesVsSurroundings
  );
  const max = Math.max(1, ...values);
  const baselinePercent = (1 / max) * 100;
  const districtName = data.districtBaseline?.signguName ?? '자치구';

  return (
    <SectionCard
      title="자치구 대비 특화 업종"
      description={`${districtName} 전체와 비교했을 때 이 반경에 유난히 많은 업종입니다. 기준선(1.0)은 ${districtName} 평균과 같은 비중이라는 뜻입니다.`}
    >
      <div className="ca-spec-wrap">
        <div
          className="ca-spec-baseline"
          style={{ left: `calc(${baselinePercent}% + var(--ca-spec-label-w))` }}
        >
          <span className="ca-spec-baseline-label">1.0</span>
        </div>
        {data.districtSpecialization.map((item) => (
          <div key={item.code} className="ca-bar-row">
            <span className="ca-bar-label">{item.name}</span>
            <div className="ca-bar-track">
              <div
                className="ca-bar-fill"
                style={{
                  width: `${(item.timesVsSurroundings / max) * 100}%`,
                  backgroundColor: colors.brand.dark,
                }}
              />
            </div>
            <span className="ca-bar-note">{item.note}</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

/** B. 추천/비추천 업종별 경쟁 지표 카드 */
function IndustryCompetitionCard({
  item,
  recommended,
  data,
}: {
  item: RecommendedIndustry;
  recommended: boolean;
  data: CommercialAreaData;
}) {
  const code = RECOMMENDED_NAME_TO_MIDDLE_CODE[item.name];
  const middle: CommercialAreaMiddleCategory | undefined = code
    ? data.byMiddleForRecommendations.find((m) => m.code === code)
    : undefined;

  useEffect(() => {
    if (!middle) {
      console.warn(
        `[CompetitorAnalysisSection] "${item.name}" 업종은 상권 경쟁 데이터에 매칭되지 않았습니다(중분류 코드 매핑 없음 또는 조회 실패).`
      );
    }
  }, [middle, item.name]);

  const radiusLabel = `반경 ${(
    data.lqBaseline.appliedRadiusM ?? data.lqBaseline.requestedRadiusM
  ).toLocaleString('ko-KR')}m 안에서`;
  const districtLabel = data.districtBaseline
    ? `${data.districtBaseline.signguName} 전체와 비교하면`
    : '자치구 비교';

  return (
    <div
      className="ca-industry-card"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <div className="ca-industry-head">
        <span
          className={`ca-industry-name ${outfit.className} font-bold`}
          style={{ color: colors.neutral.black }}
        >
          {item.name}
        </span>
        <Badge
          style={{
            backgroundColor: recommended
              ? `${colors.brand.primary}1A`
              : `${colors.status.notRecommend}1A`,
            color: recommended ? colors.brand.dark : colors.status.notRecommend,
            fontFamily: 'inherit',
            textTransform: 'none',
            letterSpacing: 'normal',
            fontSize: fluid(9, 11),
          }}
        >
          {recommended ? '추천' : '비추천'}
        </Badge>
      </div>

      {!middle ? (
        <p className="ca-empty-note">경쟁 데이터 매칭 안 됨</p>
      ) : (
        <>
          <p className="ca-industry-counts">
            동종 점포 <strong>{middle.sameTypeCount}</strong>개 · 이종 점포{' '}
            <strong>{middle.diffTypeCount}</strong>개
          </p>
          <DivergingBar eyebrow={radiusLabel} value={middle.lq} />
          <DivergingBar
            eyebrow={districtLabel}
            value={data.districtBaseline ? middle.lqDistrict : null}
            unavailableLabel="자치구 비교 자료 없음"
          />
        </>
      )}
    </div>
  );
}

function IndustryCompetitionGrid({ data }: { data: CommercialAreaData }) {
  const recommended = mockReportData.recommended;
  const notRecommended = mockReportData.notRecommended;

  return (
    <SectionCard
      title="업종별 경쟁 지표"
      description="추천·비추천 업종 각각이 이 상권에서 얼마나 밀집해 있는지 보여줍니다. lq는 좋고 나쁨의 지표가 아니라 기준 대비 배수입니다."
    >
      <div className="ca-industry-grid">
        {recommended.map((item) => (
          <IndustryCompetitionCard
            key={`rec-${item.rank}`}
            item={item}
            recommended
            data={data}
          />
        ))}
        {notRecommended.map((item) => (
          <IndustryCompetitionCard
            key={`not-${item.rank}`}
            item={item}
            recommended={false}
            data={data}
          />
        ))}
      </div>
    </SectionCard>
  );
}

export default function CompetitorAnalysisSection() {
  const data = mockReportData.commercialArea as CommercialAreaData;
  const visibility = getSectionVisibility(data.status);

  if (visibility === 'hidden') {
    return (
      <div className="ca-root ca-root-empty">
        <p className="ca-empty-note">
          {data.status === 'error'
            ? '경쟁업체 데이터를 불러오지 못했습니다.'
            : '이 위치는 경쟁업체 분석에 필요한 자료가 없습니다.'}
        </p>
      </div>
    );
  }

  return (
    <div className="ca-root flex w-full flex-col items-start">
      <RadiusGrowthChart data={data} />
      <div className="ca-major-diversity-row">
        <div className="ca-major-category-col">
          <MajorCategoryDonut data={data} />
        </div>
        <div className="ca-diversity-col">
          <DiversityStat data={data} />
        </div>
      </div>
      <FranchiseDonut data={data} />
      <TopByCountBars data={data} />
      <DistrictSpecializationBars data={data} />
      <IndustryCompetitionGrid data={data} />

      {shouldShowWarnings(data.status) && data.warnings.length > 0 && (
        <ul className="ca-warnings">
          {data.warnings.map((warning) => (
            <li key={warning}>※ {warning}</li>
          ))}
        </ul>
      )}

      <p className="ca-source">
        자료출처: 소상공인시장진흥공단 - 상가(상권)정보 (공공누리 제1유형)
        <br />
        자료출처: 공정거래위원회 - 브랜드별 가맹점 현황 (공공누리 제1유형)
        <br />
        {data.dataReferenceDate}
      </p>

      {/*
        구간별로 달라지는 값은 전부 이 블록 하나에서만 관리한다(위 마크업에는
        크기 관련 Tailwind 클래스를 달지 않는다). Badge만 공용 컴포넌트라
        fluid() inline style을 병행한다(OpenCloseTrendSection.tsx와 동일 원칙).

        레이아웃 구조가 바뀌는 지점(업종 카드 1열 ↔ 2열)만 1024px에서
        grid-template-columns를 교체하고, 나머지는 375px→1440px 한 구간을
        clamp() 하나로 보간한다.
      */}
      <style jsx global>{`
        .ca-root {
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
        .ca-root-empty {
          align-items: center;
          justify-content: center;
          min-height: 160px;
        }

        .ca-card-head {
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
        .ca-card-title {
          font-size: clamp(15px, calc(15px + (100vw - 375px) * 0.003756), 19px);
        }
        .ca-card-desc {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          line-height: 1.5;
        }
        .ca-card-body {
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

        .ca-chart-wrap {
          width: 100%;
        }

        /*
          대분류 업종 구성 + 업종 다양성을 한 행으로 묶는다. 767px 이하는
          .ca-root와 같은 세로 stack(각자 독립된 SectionCard가 그대로
          위아래로 쌓인다)을 유지하고, 768px부터 가로로 붙인다. gap은
          .ca-root의 섹션 간 간격과 동일한 clamp식을 재사용해 다른 섹션과
          리듬이 어긋나지 않게 한다.

          "대분류 업종 구성"은 도넛+범례(최대 9줄)라 콘텐츠가 더 많고,
          "업종 다양성"은 큰 숫자 한 줄 + 캡션 한 줄뿐이라 3:2 비율로
          나눠 전자를 더 넓게 잡는다. 가로 배치에서는 flex 기본값
          align-items:stretch로 두 SectionCard의 높이가 자동으로
          맞춰지므로, 짧은 "업종 다양성" 카드 안쪽 콘텐츠만 별도로
          세로 중앙 정렬해 빈 공간이 위쪽에 쏠려 보이지 않게 한다
          (.ca-card-body는 다른 모든 섹션이 공유하는 클래스라 여기서
          직접 건드리지 않고, .ca-diversity-col 하위로 스코프를 좁혀서만
          override한다).
        */
        .ca-major-diversity-row {
          display: flex;
          flex-direction: column;
          width: 100%;
          gap: clamp(16px, calc(16px + (100vw - 375px) * 0.007512), 24px);
        }
        .ca-major-category-col,
        .ca-diversity-col {
          width: 100%;
          min-width: 0;
        }
        @media (min-width: 768px) {
          .ca-major-diversity-row {
            flex-direction: row;
            align-items: stretch;
          }
          .ca-major-category-col {
            flex: 3 1 0%;
          }
          .ca-diversity-col {
            flex: 2 1 0%;
            display: flex;
            flex-direction: column;
          }
          .ca-diversity-col .ca-card {
            flex: 1 1 auto;
            display: flex;
            flex-direction: column;
          }
          .ca-diversity-col .ca-card-body {
            flex: 1 1 auto;
            justify-content: center;
          }
        }

        /* ---- 도넛(대분류 구성 / 프랜차이즈) ---- */
        .ca-donut-wrap {
          display: flex;
          width: 100%;
          flex-direction: column;
          gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 14px);
        }
        .ca-donut-chart {
          width: 100%;
        }
        .ca-donut-legend {
          display: grid;
          grid-template-columns: 1fr;
          gap: 6px;
          width: 100%;
        }
        .ca-donut-legend-row {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .ca-donut-swatch {
          width: 10px;
          height: 10px;
          border-radius: 3px;
          flex: 0 0 auto;
        }
        .ca-donut-legend-name {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1 1 auto;
          min-width: 0;
        }
        .ca-donut-legend-value {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
          flex: 0 0 auto;
          white-space: nowrap;
        }
        @media (min-width: 640px) {
          .ca-donut-wrap {
            flex-direction: row;
            align-items: center;
          }
          .ca-donut-chart {
            width: clamp(140px, calc(140px + (100vw - 640px) * 0.05), 180px);
            flex: 0 0 auto;
          }
          .ca-donut-legend {
            flex: 1 1 auto;
          }
        }

        /* ---- 업종 다양성 stat ---- */
        .ca-diversity-stat {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .ca-diversity-value {
          font-weight: 700;
          font-size: clamp(28px, calc(28px + (100vw - 375px) * 0.007512), 40px);
        }
        .ca-diversity-unit {
          font-size: clamp(14px, calc(14px + (100vw - 375px) * 0.001878), 16px);
          color: var(--color-gray-400);
          margin-left: 4px;
        }
        .ca-diversity-caption {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          color: var(--color-gray-500);
        }

        /* ---- 프랜차이즈 caveat ---- */
        .ca-franchise-caveat {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
          line-height: 1.5;
        }
        .ca-franchise-caveat strong {
          color: ${colors.neutral.black};
        }

        /* ---- 가로 막대(TOP10 공통) ---- */
        .ca-bar-row {
          display: grid;
          width: 100%;
          align-items: center;
          grid-template-columns:
            clamp(96px, calc(96px + (100vw - 375px) * 0.037559), 136px)
            minmax(0, 1fr);
          column-gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 12px);
          row-gap: 2px;
          padding-block: clamp(
            6px,
            calc(6px + (100vw - 375px) * 0.002817),
            9px
          );
        }
        .ca-bar-label {
          grid-column: 1;
          grid-row: 1 / span 2;
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .ca-bar-track {
          grid-column: 2;
          grid-row: 1;
          height: 8px;
          border-radius: 999px;
          background-color: ${colors.neutral.border};
          overflow: hidden;
        }
        .ca-bar-fill {
          height: 100%;
          border-radius: 999px;
        }
        .ca-bar-note {
          grid-column: 2;
          grid-row: 2;
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
        }

        /* ---- 자치구 특화 TOP10 기준선 ---- */
        .ca-spec-wrap {
          --ca-spec-label-w: clamp(
            96px,
            calc(96px + (100vw - 375px) * 0.037559),
            136px
          );
          position: relative;
          width: 100%;
        }
        .ca-spec-baseline {
          position: absolute;
          top: 0;
          bottom: 0;
          width: 1px;
          background-color: var(--color-gray-300);
          z-index: 1;
        }
        .ca-spec-baseline-label {
          position: absolute;
          top: -2px;
          left: 4px;
          font-size: 10px;
          color: var(--color-gray-400);
          white-space: nowrap;
        }

        .ca-empty-note {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.001878), 14px);
          color: var(--color-gray-500);
          padding-block: 8px;
        }

        /* ---- B. 업종별 경쟁 지표 카드 ---- */
        .ca-industry-grid {
          display: grid;
          grid-template-columns: 1fr;
          width: 100%;
          gap: clamp(10px, calc(10px + (100vw - 375px) * 0.005634), 16px);
        }
        @media (min-width: 1024px) {
          .ca-industry-grid {
            grid-template-columns: 1fr 1fr;
          }
        }
        .ca-industry-card {
          display: flex;
          flex-direction: column;
          width: 100%;
          min-width: 0;
          border-width: 1px;
          border-style: solid;
          border-radius: 10px;
          gap: clamp(8px, calc(8px + (100vw - 375px) * 0.002817), 11px);
          padding: clamp(12px, calc(12px + (100vw - 375px) * 0.005634), 18px);
        }
        .ca-industry-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }
        .ca-industry-name {
          font-size: clamp(13px, calc(13px + (100vw - 375px) * 0.002817), 16px);
        }
        .ca-industry-counts {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          color: var(--color-gray-500);
        }
        .ca-industry-counts strong {
          color: ${colors.neutral.black};
        }

        /* 다이버징 바(lq / lq_district) 자체 스타일은 DivergingBar.tsx가
           자기 컴포넌트 트리에 직접 <style jsx global>로 갖고 있어 여기서는
           정의하지 않는다(중복 정의를 피하고, 다른 탭에서 재사용될 때도
           항상 함께 따라오게 하기 위함). */

        .ca-warnings {
          display: flex;
          flex-direction: column;
          gap: 2px;
          width: 100%;
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-500);
          padding-top: 4px;
        }

        .ca-source {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-400);
          line-height: 1.6;
        }
      `}</style>
    </div>
  );
}
