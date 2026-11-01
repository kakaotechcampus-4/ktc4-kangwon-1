'use client';

import { useEffect, useRef, type CSSProperties } from 'react';
import styles from './PopulationBarChart.module.css';

export interface PopulationBarPoint {
  label: string;
  value: number;
  /** 라벨 옆에 * 를 붙여 각주(추정 안내)와 이어 준다. */
  footnote?: boolean;
}

/** 0부터 시작하는 눈금. 최댓값의 1.1배를 덮는 1·2·2.5·5 배수 간격으로 3~4칸을 만든다. */
function niceTicks(maximum: number): number[] {
  if (maximum <= 0) return [0, 1];
  const raw = (maximum * 1.1) / 3;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step =
    [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ??
    10 * power;
  const count = Math.ceil((maximum * 1.1) / step);
  return Array.from({ length: count + 1 }, (_, i) => i * step);
}

/**
 * 리포트용 세로 막대 차트. 눈금·기준선을 그리고, highlightIndex 하나만 강조한다.
 * 강조는 "의미가 있을 때만"(예: 최신 분기) 쓰고, 값이 크다는 이유로는 쓰지 않는다.
 */
export default function PopulationBarChart({
  data,
  label,
  unit,
  highlightIndex,
  highlightTag,
  annotation,
}: {
  data: PopulationBarPoint[];
  label: string;
  unit: string;
  highlightIndex?: number;
  highlightTag?: string;
  /** 강조 막대 값 위에 붙는 짧은 표시(예: ▼ 4.6%) */
  annotation?: string;
}) {
  const chartRef = useRef<HTMLDivElement>(null);
  const ticks = niceTicks(Math.max(0, ...data.map((point) => point.value)));
  const ceiling = ticks[ticks.length - 1];

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (!('IntersectionObserver' in window)) {
      chart.dataset.visible = 'true';
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          chart.dataset.visible = 'true';
          observer.disconnect();
        }
      },
      { threshold: 0.2 }
    );
    observer.observe(chart);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={chartRef}
      className={styles.chart}
      data-visible="false"
      role="img"
      aria-label={`${label}: ${data
        .map((p) => `${p.label} ${p.value.toLocaleString('ko-KR')}명`)
        .join(', ')}`}
    >
      <p className={styles.unit} aria-hidden="true">
        {unit}
      </p>
      <div className={styles.body} aria-hidden="true">
        <div className={styles.axis}>
          {ticks.map((tick) => (
            <span key={tick} style={{ bottom: `${(tick / ceiling) * 100}%` }}>
              {tick.toLocaleString('ko-KR')}
            </span>
          ))}
        </div>
        <div className={styles.plot}>
          {ticks.map((tick) => (
            <span
              key={tick}
              className={`${styles.grid} ${tick === 0 ? styles.baseline : ''}`}
              style={{ bottom: `${(tick / ceiling) * 100}%` }}
            />
          ))}
          <div
            className={styles.columns}
            style={{
              gridTemplateColumns: `repeat(${Math.max(1, data.length)}, minmax(0, 1fr))`,
            }}
          >
            {data.map((point, index) => {
              const strong = index === highlightIndex;
              return (
                <div className={styles.column} key={point.label}>
                  <div
                    className={styles.barGroup}
                    style={
                      {
                        height: `${(point.value / ceiling) * 100}%`,
                        '--bar-delay': `${index * 65}ms`,
                      } as CSSProperties
                    }
                  >
                    <span
                      className={`${styles.value} ${strong ? styles.valueStrong : ''}`}
                    >
                      {strong && annotation && (
                        <em className={styles.annotation}>{annotation}</em>
                      )}
                      {point.value.toLocaleString('ko-KR')}
                    </span>
                    <div
                      className={`${styles.bar} ${
                        highlightIndex === undefined
                          ? ''
                          : strong
                            ? styles.barStrong
                            : styles.barMuted
                      }`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <span />
        <div
          className={styles.labels}
          style={{
            gridTemplateColumns: `repeat(${Math.max(1, data.length)}, minmax(0, 1fr))`,
          }}
        >
          {data.map((point, index) => (
            <span
              key={point.label}
              className={index === highlightIndex ? styles.labelStrong : ''}
            >
              {point.footnote ? (
                // 각주 표시(*)가 마지막 단어와 떨어져 줄바꿈되지 않게 묶는다.
                <>
                  {point.label.slice(0, point.label.lastIndexOf(' ') + 1)}
                  <span className={styles.nowrap}>
                    {point.label.slice(point.label.lastIndexOf(' ') + 1)}
                    <sup>*</sup>
                  </span>
                </>
              ) : (
                point.label.replace(/(\d{4}년)\s*/, '$1\n')
              )}
              {index === highlightIndex && highlightTag && (
                <b className={styles.tag}>{highlightTag}</b>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
