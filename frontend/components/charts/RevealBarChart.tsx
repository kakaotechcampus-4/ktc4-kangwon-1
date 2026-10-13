'use client';

import { useEffect, useRef, type CSSProperties } from 'react';
import styles from './RevealBarChart.module.css';

export default function RevealBarChart({
  data,
  label,
}: {
  data: { label: string; value: number }[];
  label: string;
}) {
  const chartRef = useRef<HTMLDivElement>(null);
  const maximum = Math.max(0, ...data.map((point) => point.value));
  const ceiling = maximum > 0 ? Math.ceil((maximum * 1.15) / 1000) * 1000 : 1;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // 관찰 대상은 변형하지 않고 막대만 바닥을 기준으로 늘립니다.
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
      aria-label={`${label}: ${data.map((point) => `${point.label} ${point.value.toLocaleString('ko-KR')}명`).join(', ')}`}
    >
      <div className={styles.unit} aria-hidden="true">
        단위: 명/일
      </div>
      <div
        className={styles.columns}
        style={{
          gridTemplateColumns: `repeat(${Math.max(1, data.length)}, minmax(0, 1fr))`,
        }}
        aria-hidden="true"
      >
        {data.map((point, index) => (
          <div className={styles.column} key={point.label}>
            <div className={styles.plot}>
              <div
                className={styles.barGroup}
                style={
                  {
                    height: `${Math.max(0, point.value / ceiling) * 100}%`,
                    '--bar-delay': `${index * 65}ms`,
                  } as CSSProperties
                }
              >
                <span className={styles.value}>
                  {point.value.toLocaleString('ko-KR')}
                </span>
                <div
                  className={`${styles.bar} ${index === data.length - 1 ? styles.latest : ''}`}
                />
              </div>
            </div>
            <span className={styles.label}>
              {point.label.replace(/(\d{4}년)\s*/, '$1\n')}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
