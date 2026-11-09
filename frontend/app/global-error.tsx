'use client';

import type { CSSProperties } from 'react';
import Link from 'next/link';
import { colors } from '@/styles/tokens';

const button: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 12,
  fontFamily: 'inherit',
  fontSize: 14,
  lineHeight: 1.43,
  textDecoration: 'none',
  cursor: 'pointer',
};

const styles = {
  body: {
    margin: 0,
    minHeight: '100vh',
    backgroundColor: colors.neutral.background,
    color: colors.brand.dark,
    fontFamily: "'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif",
    lineHeight: 1.5,
    wordBreak: 'keep-all',
  },
  main: {
    display: 'flex',
    flexDirection: 'column',
    gap: 32,
    maxWidth: 880,
    margin: '0 auto',
    padding: '56px clamp(16px, 5vw, 32px) 96px',
  },
  heading: { display: 'flex', flexDirection: 'column', gap: 12 },
  eyebrow: {
    margin: 0,
    color: colors.brand.primary,
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: '0.08em',
  },
  title: {
    margin: 0,
    fontSize: 'clamp(26px, 3vw, 42px)',
    fontWeight: 800,
    letterSpacing: '-0.04em',
  },
  description: { margin: 0, color: colors.text.secondary, fontSize: 16 },
  card: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 16,
    padding: 28,
    borderRadius: 24,
    border: `1px solid ${colors.neutral.border}`,
    backgroundColor: colors.neutral.white,
    boxShadow: '0 18px 40px rgba(16, 35, 58, 0.06)',
  },
  cardTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 800,
    letterSpacing: '-0.02em',
  },
  cardBody: { margin: 0, color: colors.text.secondary, fontSize: 15 },
  actions: { display: 'flex', flexWrap: 'wrap', gap: 12 },
  retry: {
    ...button,
    padding: '14px 28px',
    border: `1.5px solid ${colors.brand.primary}`,
    backgroundColor: colors.brand.primary,
    color: colors.neutral.white,
    fontWeight: 700,
    boxShadow: '0 8px 18px rgba(36, 83, 214, 0.2)',
  },
  home: {
    ...button,
    padding: '14px 20px',
    border: `1.5px solid ${colors.brand.dark}`,
    backgroundColor: colors.neutral.white,
    color: colors.brand.dark,
    fontWeight: 600,
  },
} satisfies Record<string, CSSProperties>;

export default function GlobalErrorPage({ retry }: { retry: () => void }) {
  return (
    <html lang="ko">
      <body style={styles.body}>
        <main style={styles.main}>
          <div style={styles.heading}>
            <p style={styles.eyebrow}>SOMETHING WENT WRONG</p>
            <h1 style={styles.title}>화면을 여는 중에 문제가 생겼어요</h1>
            <p style={styles.description}>잠시 후 다시 시도해 주세요.</p>
          </div>
          <div style={styles.card}>
            <p style={styles.cardTitle}>다시 시도해 주세요</p>
            <p style={styles.cardBody}>
              같은 문제가 계속되면 홈에서 다시 시작해 주세요.
            </p>
            <div style={styles.actions}>
              <button type="button" onClick={retry} style={styles.retry}>
                다시 시도
              </button>
              <Link href="/" style={styles.home}>
                홈으로
              </Link>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}
