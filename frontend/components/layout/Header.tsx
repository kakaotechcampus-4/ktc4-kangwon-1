'use client';

import type { CSSProperties } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { colors } from '@/styles/tokens';

const navLinks = [
  { label: '홈', href: '/' },
  { label: '공실 분석', href: '/vacancy-input' },
  { label: '리포트', href: '/report' },
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
      <div className="mx-auto grid h-14 w-full max-w-[1440px] grid-cols-3 items-center px-5 sm:px-8">
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
          {navLinks.map(({ label, href }) => {
            const active = pathname === href;

            return (
              <Link
                key={label}
                href={href}
                className="group relative flex flex-col items-center justify-center px-4 py-1.5"
              >
                <p
                  className={`text-[15px] leading-[22.5px] whitespace-nowrap transition-colors ${
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

        <div />
      </div>
    </header>
  );
}
