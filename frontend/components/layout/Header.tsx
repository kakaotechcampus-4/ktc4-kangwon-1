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

export default function Header() {
  const pathname = usePathname();

  return (
    <header
      className="flex w-full flex-col items-start"
      style={{
        backgroundColor: colors.neutral.white,
        borderBottom: `1px solid ${colors.neutral.border}`,
      }}
    >
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-4 sm:grid sm:grid-cols-3 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5 justify-self-start">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md">
            <Image
              src="/images/logo-mark.svg"
              alt="chum.ai 로고"
              width={25}
              height={28}
            />
          </div>
          <p
            className="text-xl font-bold tracking-[0.5px]"
            style={{ color: colors.neutral.black }}
          >
            chum
            <span className="font-light">.</span>
            <span
              className="font-normal"
              style={{ color: colors.brand.primary }}
            >
              ai
            </span>
          </p>
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
                className="group relative flex flex-col items-center justify-center px-2.5 py-1.5 sm:px-4"
              >
                <p
                  className={`text-15 whitespace-nowrap transition-colors ${
                    active
                      ? 'font-semibold'
                      : 'font-normal text-gray-500 group-hover:text-[var(--nav-accent)]'
                  }`}
                  style={active ? { color: colors.brand.dark } : undefined}
                >
                  {label}
                </p>
                {active ? (
                  <span
                    className="absolute bottom-0 h-0.5 w-3 rounded-full"
                    style={{ backgroundColor: colors.brand.dark }}
                  />
                ) : (
                  <span
                    className="absolute bottom-0 h-0.5 w-3 scale-x-0 rounded-full opacity-0 transition-all duration-150 group-hover:scale-x-100 group-hover:opacity-100"
                    style={{ backgroundColor: colors.brand.primary }}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="hidden sm:block" />
      </div>
    </header>
  );
}
