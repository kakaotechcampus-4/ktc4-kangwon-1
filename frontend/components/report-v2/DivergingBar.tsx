'use client';

import { DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

/*
 * CompetitorAnalysisSection.tsx(lq/lq_district)와 FloatingPopulationSection.tsx
 * (age_index)가 공유하는 "1.0 기준 배수" 다이버징 바. 둘 다 좋고 나쁨의 지표가
 * 아니라 단순 비율/밀집도라, 위험·양호 같은 판단 색상을 쓰지 않고 "기준보다
 * 많음/적음"을 명도 차이로만 구분한다.
 *
 * <style jsx global>은 이 컴포넌트를 렌더링하는 트리가 마운트될 때 함께
 * 주입되고 언마운트되면 정리되므로, 스타일을 이 파일 안에 함께 둬야 다른
 * 탭(다른 마운트 트리)에서도 그대로 재사용된다 — 호출하는 쪽 파일의
 * <style jsx global>에 이 클래스들을 옮겨두면 그 파일이 마운트되지 않는 한
 * 스타일이 붙지 않는다.
 */
const ABOVE_COLOR = colors.brand.dark;
const BELOW_COLOR = 'var(--color-gray-400)';
const SCALE_CAP = 1.5; // |value-1|이 이 값 이상이면 바가 꽉 찬 것으로 그린다.

export function formatDivergingValue(
  value: number | null,
  suffix = '배',
): string {
  // null은 "비교 기준 없음", 0.0은 "기준은 있지만 배수가 0"이라 문구가
  // 완전히 달라야 한다. === null로만 판별해 0.0이 이 분기로 새지 않게 한다.
  if (value === null) {
    return '비교 불가';
  }
  return `${value.toFixed(2)}${suffix}`;
}

export default function DivergingBar({
  eyebrow,
  value,
  unavailableLabel,
  suffix,
}: {
  eyebrow: string;
  value: number | null;
  unavailableLabel?: string;
  suffix?: string;
}) {
  const fillPercent =
    value === null ? 0 : Math.min(1, Math.abs(value - 1) / SCALE_CAP) * 100;
  const isAbove = value !== null && value >= 1;

  return (
    <div className="divbar">
      <p className="divbar-eyebrow">{eyebrow}</p>
      {value === null ? (
        <p className="divbar-unavailable">
          {unavailableLabel ?? '비교 불가'}
        </p>
      ) : (
        <div className="divbar-row">
          <div className="divbar-track">
            <div className="divbar-half divbar-half-left">
              <div
                className="divbar-fill"
                style={{
                  width: !isAbove ? `${fillPercent}%` : '0%',
                  backgroundColor: BELOW_COLOR,
                }}
              />
            </div>
            <div className="divbar-center">
              <span className="divbar-center-label">1.0</span>
            </div>
            <div className="divbar-half divbar-half-right">
              <div
                className="divbar-fill"
                style={{
                  width: isAbove ? `${fillPercent}%` : '0%',
                  backgroundColor: ABOVE_COLOR,
                }}
              />
            </div>
          </div>
          <span className={`divbar-value ${dmMono.className}`}>
            {formatDivergingValue(value, suffix)}
          </span>
        </div>
      )}

      <style jsx global>{`
        .divbar {
          display: flex;
          flex-direction: column;
          gap: 4px;
          width: 100%;
        }
        .divbar-eyebrow {
          font-size: clamp(
            10px,
            calc(10px + (100vw - 375px) * 0.001878),
            12px
          );
          color: var(--color-gray-500);
        }
        .divbar-unavailable {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.001878),
            13px
          );
          color: var(--color-gray-400);
          font-style: italic;
        }
        .divbar-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .divbar-track {
          flex: 1 1 auto;
          min-width: 0;
          display: flex;
          align-items: center;
          height: 14px;
          background-color: ${colors.neutral.border};
          border-radius: 999px;
        }
        .divbar-half {
          flex: 1 1 50%;
          height: 100%;
          display: flex;
          align-items: center;
          /* overflow는 트랙 전체가 아니라 각 절반에만 걸어, 아래 1.0 기준
             라벨(.divbar-center-label, 트랙 바깥으로 살짝 내려오는 절대배치
             요소)이 잘리지 않게 한다. */
          overflow: hidden;
        }
        .divbar-half-left {
          justify-content: flex-end;
          border-top-left-radius: 999px;
          border-bottom-left-radius: 999px;
        }
        .divbar-half-right {
          justify-content: flex-start;
          border-top-right-radius: 999px;
          border-bottom-right-radius: 999px;
        }
        .divbar-fill {
          height: 100%;
        }
        .divbar-center {
          position: relative;
          flex: 0 0 auto;
          width: 2px;
          height: 100%;
          background-color: var(--color-gray-400);
        }
        .divbar-center-label {
          position: absolute;
          top: 16px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 9px;
          color: var(--color-gray-400);
          white-space: nowrap;
        }
        .divbar-value {
          flex: 0 0 auto;
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.001878),
            13px
          );
          color: ${colors.neutral.black};
          width: 44px;
          text-align: right;
        }
      `}</style>
    </div>
  );
}
