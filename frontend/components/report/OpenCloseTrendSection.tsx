'use client';

import { useState } from 'react';
import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import {
  mockReportData,
  type LifecycleConfidence,
  type OpenCloseIndustryIndex,
} from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

/**
 * 375px에서 min, 1440px에서 max가 되도록 선형 보간한 clamp 문자열.
 * Badge/ProgressBar처럼 자체 Tailwind 크기 클래스를 가진 공용 컴포넌트는
 * 아래 <style jsx global> 규칙과 specificity가 같아 순서에 따라 승자가
 * 갈리므로, 그쪽에는 이 헬퍼로 만든 값을 inline style로 넣어 단일 소스를
 * 유지한다(StatsRow.tsx에서 쓰는 방식과 동일). 이 파일이 직접 렌더링하는
 * 엘리먼트는 반대로 style jsx global 한 곳에서만 크기를 지정한다.
 */
const fluid = (min: number, max: number) =>
  `clamp(${min}px, calc(${min}px + (100vw - 375px) * ${(
    (max - min) /
    1065
  ).toFixed(6)}), ${max}px)`;

const recommendedNames = new Set(
  mockReportData.recommended.map((item) => item.name)
);

const indexData = mockReportData.openCloseIndex;

const confidenceLabels: Record<LifecycleConfidence, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
};

type Band = {
  label: string;
  color: string;
};

// 요구 구간: 0~30 위험 / 30~60 보통 / 60~100 양호.
function getBand(score: number): Band {
  if (score < 30) {
    return { label: '위험', color: colors.status.notRecommend };
  }
  if (score < 60) {
    return { label: '보통', color: colors.accent.orange };
  }
  return { label: '양호', color: colors.brand.primary };
}

function isRecommended(item: OpenCloseIndustryIndex) {
  return recommendedNames.has(item.industryName);
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card
      className="oc-card w-full"
      style={{
        padding: 0,
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow:
          '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
      }}
    >
      <div
        className="oc-card-head flex w-full flex-col items-start"
        style={{ borderBottom: `1px solid ${colors.neutral.border}` }}
      >
        <p
          className={`oc-card-title ${outfit.className} font-bold`}
          style={{ color: colors.neutral.black }}
        >
          {title}
        </p>
        <p className="oc-card-desc text-gray-500">{description}</p>
      </div>
      <div className="oc-card-body flex w-full flex-col items-start">
        {children}
      </div>
    </Card>
  );
}

/**
 * 순증감(▲/▼/– + 색) 표시를 StoreStatus·StabilityGauge 둘 다에서 쓴다.
 * 양수는 brand.primary, 음수는 status.notRecommend, 0이면 색 없이 "–"만
 * 보여준다 — 부호는 음수 값 자체가 이미 "-"를 포함해 나오므로 따로
 * 안 붙이고, 양수일 때만 "+"를 붙인다.
 */
function NetChangeDisplay({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const positive = value > 0;
  const negative = value < 0;
  const color = positive
    ? colors.brand.primary
    : negative
      ? colors.status.notRecommend
      : undefined;

  return (
    <span className={className} style={{ color }}>
      {positive ? '▲' : negative ? '▼' : '–'}
      {value !== 0 && (
        <span>
          {positive ? '+' : ''}
          {value}
        </span>
      )}
    </span>
  );
}

function RecommendBadge({ recommended }: { recommended: boolean }) {
  return (
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
        paddingInline: fluid(5, 8),
      }}
    >
      {recommended ? '추천' : '비추천'}
    </Badge>
  );
}

/** 2. 점포 현황 */
function StoreStatus() {
  // 개업/폐업 미니 막대는 절대값이 아니라 10개 업종 중 최대값 대비 비율로
  // 그린다. 그래야 한 자릿수 건수 차이도 길이로 구분된다.
  const maxOpen = Math.max(...indexData.map((item) => item.openCount));
  const maxClose = Math.max(...indexData.map((item) => item.closeCount));

  return (
    <SectionCard
      title="점포 현황"
      description="추천·비추천 10개 업종의 연간 개업·폐업 건수와 순증감입니다."
    >
      <div className="oc-store-row oc-store-head" aria-hidden="true">
        <span className="oc-store-name-cell">업종</span>
        <span className="oc-store-count-cell">점포수</span>
        <span className="oc-store-open-cell">개업</span>
        <span className="oc-store-close-cell">폐업</span>
        <span className="oc-store-net-cell">순증감</span>
      </div>

      {indexData.map((item) => {
        const recommended = isRecommended(item);

        return (
          <div
            key={item.industryCode}
            className="oc-store-row"
            style={{ borderTop: `1px solid ${colors.neutral.border}` }}
          >
            <span className="oc-store-name-cell">
              <span className="oc-store-name">{item.industryName}</span>
              <RecommendBadge recommended={recommended} />
            </span>

            <span className="oc-store-count-cell">
              <span className="oc-cell-label">점포수</span>
              <span className={`oc-num ${dmMono.className}`}>
                {item.storeCount}
              </span>
            </span>

            <span className="oc-store-open-cell">
              <span className="oc-cell-label">개업</span>
              <ProgressBar
                className="oc-mini-bar"
                value={(item.openCount / maxOpen) * 100}
                color="primary"
              />
              <span className={`oc-num oc-num-tail ${dmMono.className}`}>
                {item.openCount}
              </span>
            </span>

            <span className="oc-store-close-cell">
              <span className="oc-cell-label">폐업</span>
              <ProgressBar
                className="oc-mini-bar"
                value={(item.closeCount / maxClose) * 100}
                color="danger"
              />
              <span className={`oc-num oc-num-tail ${dmMono.className}`}>
                {item.closeCount}
              </span>
            </span>

            <NetChangeDisplay
              value={item.netChange}
              className={`oc-store-net-cell ${dmMono.className}`}
            />
          </div>
        );
      })}
    </SectionCard>
  );
}

/** 3·4. 폐업률 / 회전율 공통 가로 막대 리스트 */
function MetricBarList({
  title,
  description,
  unit,
  pick,
}: {
  title: string;
  description: string;
  unit: string;
  pick: (item: OpenCloseIndustryIndex) => number;
}) {
  const sorted = [...indexData].sort((a, b) => pick(b) - pick(a));
  // 막대 길이는 최댓값을 100%로 둔 상대값이다. 폐업률(최대 22.7%)을 그대로
  // 퍼센트 폭으로 쓰면 모든 막대가 1/5 미만이라 비교가 안 되기 때문.
  const max = Math.max(...sorted.map(pick));

  return (
    <SectionCard title={title} description={description}>
      {sorted.map((item) => {
        const recommended = isRecommended(item);
        const value = pick(item);

        return (
          <div key={item.industryCode} className="oc-bar-row">
            <span className="oc-bar-label">{item.industryName}</span>
            <ProgressBar
              className="oc-bar-track"
              value={(value / max) * 100}
              color={recommended ? 'primary' : 'muted'}
            />
            <span className={`oc-bar-value ${dmMono.className}`}>
              {value}
              {unit}
            </span>
          </div>
        );
      })}

      <div className="oc-legend">
        <span className="oc-legend-item">
          <span
            className="oc-legend-swatch"
            style={{ backgroundColor: colors.brand.primary }}
          />
          추천 업종
        </span>
        <span className="oc-legend-item">
          <span
            className="oc-legend-swatch"
            style={{ backgroundColor: colors.brand.dark }}
          />
          비추천 업종
        </span>
      </div>
    </SectionCard>
  );
}

/** 1. 개폐업 안정성 */
function StabilityGauge() {
  const [selectedCode, setSelectedCode] = useState(indexData[0].industryCode);
  const selected =
    indexData.find((item) => item.industryCode === selectedCode) ??
    indexData[0];
  const band = getBand(selected.score);

  // 반원 게이지: 중심 (100,100), 반지름 82의 위쪽 반원.
  const arcLength = Math.PI * 82;
  const filled = (Math.min(100, Math.max(0, selected.score)) / 100) * arcLength;

  return (
    <SectionCard
      title="개폐업 안정성"
      description="업종을 선택하면 개폐업 지표를 종합한 안정성 점수를 보여줍니다."
    >
      <div className="oc-chip-row">
        {indexData.map((item) => {
          const active = item.industryCode === selectedCode;

          return (
            <button
              key={item.industryCode}
              type="button"
              aria-pressed={active}
              onClick={() => setSelectedCode(item.industryCode)}
              className="oc-chip"
              style={{
                backgroundColor: active
                  ? `${colors.brand.primary}1A`
                  : colors.neutral.white,
                borderColor: active
                  ? colors.brand.primary
                  : colors.neutral.border,
                color: active ? colors.brand.dark : undefined,
                fontWeight: active ? 600 : 400,
              }}
            >
              {item.industryName}
            </button>
          );
        })}
      </div>

      <div className="oc-gauge-wrap">
        <svg
          className="oc-gauge"
          viewBox="0 0 200 128"
          role="img"
          aria-label={`${selected.industryName} 안정성 점수 ${selected.score}점, ${band.label}`}
        >
          <path
            d="M 18 100 A 82 82 0 0 1 182 100"
            fill="none"
            stroke={colors.neutral.border}
            strokeWidth={16}
            strokeLinecap="round"
          />
          <path
            d="M 18 100 A 82 82 0 0 1 182 100"
            fill="none"
            stroke={band.color}
            strokeWidth={16}
            strokeLinecap="round"
            strokeDasharray={`${filled} ${arcLength}`}
          />
          <text
            x="100"
            y="88"
            textAnchor="middle"
            fontSize="38"
            fontWeight="700"
            fill={band.color}
          >
            {selected.score}
          </text>
          <text
            x="100"
            y="108"
            textAnchor="middle"
            fontSize="12"
            fill="var(--color-gray-400)"
          >
            / 100점
          </text>
          <text
            x="18"
            y="124"
            textAnchor="middle"
            fontSize="11"
            fill="var(--color-gray-400)"
          >
            0
          </text>
          <text
            x="182"
            y="124"
            textAnchor="middle"
            fontSize="11"
            fill="var(--color-gray-400)"
          >
            100
          </text>
        </svg>

        <div className="oc-gauge-meta">
          <p
            className={`oc-gauge-name ${outfit.className} font-bold`}
            style={{ color: colors.neutral.black }}
          >
            {selected.industryName}
          </p>

          <div className="oc-gauge-badges">
            <Badge
              style={{
                backgroundColor: `${band.color}1A`,
                color: band.color,
                fontFamily: 'inherit',
                textTransform: 'none',
                letterSpacing: 'normal',
                fontSize: fluid(10, 12),
              }}
            >
              {band.label}
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
              신뢰도 {confidenceLabels[selected.confidence]}
            </Badge>
          </div>

          <dl className="oc-gauge-stats">
            <div>
              <dt>폐업률</dt>
              <dd className={dmMono.className}>{selected.closeRate}%</dd>
            </div>
            <div>
              <dt>회전율</dt>
              <dd className={dmMono.className}>{selected.turnoverRate}</dd>
            </div>
            <div>
              <dt>순증감</dt>
              <dd className={dmMono.className}>
                <NetChangeDisplay value={selected.netChange} />
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </SectionCard>
  );
}

export default function OpenCloseTrendSection() {
  return (
    <div className="oc-root flex w-full flex-col items-start">
      <StabilityGauge />
      <StoreStatus />
      <MetricBarList
        title="폐업률"
        description="값이 높은 업종일수록 같은 상권에서 문을 닫는 비율이 높습니다."
        unit="%"
        pick={(item) => item.closeRate}
      />
      <MetricBarList
        title="회전율"
        description="개업과 폐업이 함께 잦은 정도입니다. 높을수록 사업자 교체가 빈번합니다."
        unit=""
        pick={(item) => item.turnoverRate}
      />

      <p className="oc-source text-gray-400">
        출처: {mockReportData.openCloseSource}
      </p>

      {/*
        구간별로 달라지는 값(폰트·여백·컬럼 폭·게이지 크기)은 전부 이 블록
        하나에서만 관리한다. 위 마크업에는 크기 관련 Tailwind 클래스를 달지
        않아, 같은 속성을 두 소스가 동시에 지정해 순서에 따라 승자가 갈리는
        문제를 원천적으로 피한다(공용 Badge/ProgressBar만 예외적으로 inline
        style + fluid() 사용 — 파일 상단 주석 참고).

        모든 값은 375px→1440px 한 구간을 clamp() 하나로 보간한다. 레이아웃
        구조가 바뀌는 지점(점포 현황 표의 5열 ↔ 세로 스택)만 768px에서
        grid-template-columns를 교체하는데, 이건 연속 보간이 불가능한
        이산적 전환이라 미디어 쿼리로 처리한다.
      */}
      <style jsx global>{`
        .oc-root {
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

        .oc-card-head {
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
        .oc-card-title {
          font-size: clamp(15px, calc(15px + (100vw - 375px) * 0.003756), 19px);
        }
        .oc-card-desc {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          line-height: 1.5;
        }
        .oc-card-body {
          padding-inline: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.00939),
            24px
          );
          padding-block: clamp(
            8px,
            calc(8px + (100vw - 375px) * 0.005634),
            14px
          );
        }

        /* ---- 2. 점포 현황 ---- */
        .oc-store-row {
          display: grid;
          width: 100%;
          align-items: center;
          column-gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 12px);
          row-gap: 6px;
          padding-block: clamp(
            10px,
            calc(10px + (100vw - 375px) * 0.001878),
            12px
          );
          /* 768px 미만: 1행에 업종명+순증감, 아래로 지표가 쌓인다. */
          grid-template-columns: minmax(0, 1fr) auto;
        }
        .oc-store-row:first-of-type {
          border-top: none !important;
        }
        .oc-store-name-cell {
          grid-column: 1;
          grid-row: 1;
          display: flex;
          align-items: center;
          gap: 6px;
          min-width: 0;
        }
        .oc-store-net-cell {
          grid-column: 2;
          grid-row: 1;
          display: flex;
          align-items: baseline;
          justify-content: flex-end;
          gap: 2px;
        }
        .oc-store-count-cell {
          grid-column: 1 / -1;
          grid-row: 2;
        }
        .oc-store-open-cell {
          grid-column: 1 / -1;
          grid-row: 3;
        }
        .oc-store-close-cell {
          grid-column: 1 / -1;
          grid-row: 4;
        }
        .oc-store-count-cell,
        .oc-store-open-cell,
        .oc-store-close-cell {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .oc-store-head {
          display: none;
        }
        /*
          본문 텍스트는 색을 반드시 명시한다. globals.css가 body에
          color: var(--foreground)를 걸어두는데, OS 다크 모드에서 이 값이
          #ededed가 되어 흰 카드 위 글자가 사실상 보이지 않기 때문이다.
          (이 프로젝트의 다른 컴포넌트들도 전부 색을 명시해 이 문제를 피한다.)
        */
        .oc-store-name {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.002817), 15px);
          font-weight: 600;
          color: ${colors.neutral.black};
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .oc-num {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.002817), 15px);
          color: ${colors.neutral.black};
        }
        .oc-cell-label {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
          color: var(--color-gray-400);
          flex: 0 0 auto;
          width: 34px;
        }
        .oc-mini-bar {
          flex: 1 1 auto;
          min-width: 0;
        }
        .oc-num-tail {
          flex: 0 0 auto;
          width: 22px;
          text-align: right;
        }
        .oc-store-net-cell {
          font-size: clamp(12px, calc(12px + (100vw - 375px) * 0.002817), 15px);
          color: var(--color-gray-400);
        }

        @media (min-width: 768px) {
          .oc-store-row {
            grid-template-columns:
              minmax(0, 1.5fr) 56px minmax(0, 1fr)
              minmax(0, 1fr) 68px;
            row-gap: 0;
          }
          .oc-store-head {
            display: grid;
            color: var(--color-gray-400);
            font-size: clamp(
              10px,
              calc(10px + (100vw - 375px) * 0.001878),
              12px
            );
            padding-block: 8px;
          }
          .oc-store-name-cell {
            grid-column: 1;
            grid-row: 1;
          }
          .oc-store-count-cell {
            grid-column: 2;
            grid-row: 1;
          }
          .oc-store-open-cell {
            grid-column: 3;
            grid-row: 1;
          }
          .oc-store-close-cell {
            grid-column: 4;
            grid-row: 1;
          }
          .oc-store-net-cell {
            grid-column: 5;
            grid-row: 1;
          }
          .oc-cell-label {
            display: none;
          }
        }

        /* ---- 3·4. 폐업률 / 회전율 ---- */
        .oc-bar-row {
          display: grid;
          width: 100%;
          align-items: center;
          grid-template-columns:
            clamp(72px, calc(72px + (100vw - 375px) * 0.04507), 120px)
            minmax(0, 1fr)
            clamp(40px, calc(40px + (100vw - 375px) * 0.011268), 52px);
          column-gap: clamp(8px, calc(8px + (100vw - 375px) * 0.003756), 12px);
          padding-block: clamp(
            7px,
            calc(7px + (100vw - 375px) * 0.002817),
            10px
          );
        }
        .oc-bar-label {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .oc-bar-track {
          min-width: 0;
        }
        .oc-bar-value {
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.002817), 14px);
          color: ${colors.neutral.black};
          text-align: right;
        }
        .oc-legend {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          padding-top: 10px;
          color: var(--color-gray-400);
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
        }
        .oc-legend-item {
          display: inline-flex;
          align-items: center;
          gap: 5px;
        }
        .oc-legend-swatch {
          width: 10px;
          height: 10px;
          border-radius: 3px;
          display: inline-block;
        }

        /* ---- 1. 개폐업 안정성 ---- */
        .oc-chip-row {
          display: flex;
          flex-wrap: wrap;
          width: 100%;
          gap: clamp(6px, calc(6px + (100vw - 375px) * 0.001878), 8px);
          padding-block: 4px 14px;
        }
        .oc-chip {
          border-width: 1px;
          border-style: solid;
          border-radius: 999px;
          cursor: pointer;
          transition:
            background-color 0.15s ease,
            border-color 0.15s ease;
          color: var(--color-gray-500);
          font-size: clamp(11px, calc(11px + (100vw - 375px) * 0.001878), 13px);
          padding-inline: clamp(
            10px,
            calc(10px + (100vw - 375px) * 0.003756),
            14px
          );
          padding-block: clamp(
            5px,
            calc(5px + (100vw - 375px) * 0.001878),
            7px
          );
        }
        .oc-gauge-wrap {
          display: flex;
          width: 100%;
          flex-wrap: wrap;
          align-items: center;
          gap: clamp(12px, calc(12px + (100vw - 375px) * 0.011268), 24px);
          padding-block: 4px 8px;
        }
        .oc-gauge {
          width: clamp(180px, calc(180px + (100vw - 375px) * 0.065728), 250px);
          height: auto;
          flex: 0 0 auto;
        }
        .oc-gauge-meta {
          display: flex;
          flex: 1 1 200px;
          min-width: 0;
          flex-direction: column;
          align-items: flex-start;
          gap: 8px;
        }
        .oc-gauge-name {
          font-size: clamp(15px, calc(15px + (100vw - 375px) * 0.003756), 19px);
        }
        .oc-gauge-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .oc-gauge-stats {
          display: flex;
          flex-wrap: wrap;
          gap: clamp(12px, calc(12px + (100vw - 375px) * 0.007512), 20px);
          padding-top: 2px;
        }
        .oc-gauge-stats div {
          display: flex;
          flex-direction: column;
          gap: 1px;
        }
        .oc-gauge-stats dt {
          color: var(--color-gray-400);
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
        }
        .oc-gauge-stats dd {
          font-size: clamp(13px, calc(13px + (100vw - 375px) * 0.002817), 16px);
          color: ${colors.neutral.black};
        }

        .oc-source {
          font-size: clamp(10px, calc(10px + (100vw - 375px) * 0.001878), 12px);
        }
      `}</style>
    </div>
  );
}
