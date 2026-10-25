'use client';

import type { CSSProperties } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { colors } from '@/styles/tokens';

const navLinks = [
  { label: '홈', href: '/', matchPaths: ['/'] },
  // "공실 분석" 탭은 주소 입력 → 상가 정보 확인 → 분석 진행 세 화면 모두에서
  // 활성 상태를 유지해야 한다(같은 흐름의 1~3단계이기 때문). 4단계인 리포트는 별도 탭.
  {
    label: '공실 분석',
    href: '/vacancy-input',
    matchPaths: ['/vacancy-input', '/building-confirm', '/analysis-progress'],
  },
  { label: '리포트', href: '/report', matchPaths: ['/report'] },
];

const navAccentStyle = {
  '--nav-accent': colors.brand.primary,
} as CSSProperties;

/** 서비스 로고 마크(public/images/logo-mark.svg) — 남색·파랑 두 쪽이 맞물린 집 모양 */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <Image
      src="/images/logo-mark.svg"
      alt=""
      aria-hidden="true"
      width={Math.round((size * 25) / 28)}
      height={size}
      className="shrink-0"
    />
  );
}

type HeaderProps = {
  /**
   * 랜딩 히어로처럼 배경 위에 겹쳐 띄울 때 true. 흰 바탕·아래 테두리 없이
   * 히어로 위에 절대 위치로 놓인다. 기본값 false라 기존 호출부는 그대로다.
   */
  overlay?: boolean;
};

export default function Header({ overlay = false }: HeaderProps) {
  const pathname = usePathname();

  return (
    <header
      className={`z-20 flex w-full flex-col items-start ${
        overlay ? 'absolute inset-x-0 top-0' : ''
      }`}
      style={
        overlay
          ? undefined
          : {
              backgroundColor: colors.neutral.white,
              borderBottom: `1px solid ${colors.neutral.border}`,
            }
      }
    >
      <div
        className={`mx-auto flex w-full max-w-[1440px] items-center justify-between px-4 sm:grid sm:grid-cols-3 sm:px-8 ${
          overlay ? 'h-20' : 'h-16'
        }`}
      >
        <Link href="/" className="flex items-center gap-2.5 justify-self-start">
          <LogoMark />
          <span
            className="text-lg font-extrabold tracking-[-0.02em]"
            style={{ color: colors.brand.dark }}
          >
            채움
          </span>
          <span className="hidden text-13 font-semibold text-[#4A5A6A] sm:inline">
            chum.ai
          </span>
        </Link>

        <nav
          className="flex items-center gap-0.5 justify-self-center sm:gap-1"
          style={navAccentStyle}
        >
          {navLinks.map(({ label, href, matchPaths }) => {
            const active = matchPaths.includes(pathname);

            return (
              <Link
                key={label}
                href={href}
                aria-current={active ? 'page' : undefined}
                className="group relative flex flex-col items-center justify-center px-2.5 py-2 sm:px-4"
              >
                <span
                  className={`text-15 whitespace-nowrap transition-colors ${
                    active
                      ? 'font-bold'
                      : 'font-medium text-[#4A5A6A] group-hover:text-[var(--nav-accent)]'
                  }`}
                  style={active ? { color: colors.brand.primary } : undefined}
                >
                  {label}
                </span>
                <span
                  className={`absolute bottom-0 h-0.5 w-4 rounded-full transition-all duration-150 ${
                    active
                      ? ''
                      : 'scale-x-0 opacity-0 group-hover:scale-x-100 group-hover:opacity-100'
                  }`}
                  style={{ backgroundColor: colors.brand.primary }}
                />
              </Link>
            );
          })}
        </nav>

        <div className="hidden justify-self-end sm:block">
          <Link
            href="/vacancy-input"
            className="inline-flex h-11 items-center gap-3 rounded-md border-[1.5px] px-4 text-15 font-bold transition-colors hover:bg-white/60"
            style={{
              borderColor: colors.brand.dark,
              color: colors.brand.dark,
            }}
          >
            분석 시작
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path
                d="M2 7h10M8 3l4 4-4 4"
                stroke="currentColor"
                strokeWidth="1.6"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
        </div>
      </div>
    </header>
  );
}
