'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Outfit } from 'next/font/google';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600'],
});

const navLinks = [
  { label: '홈', href: '/' },
  { label: '공실 분석', href: '/vacancy-input' },
  { label: '리포트', href: null },
];

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
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-8">
        <div className="flex shrink-0 items-center gap-2.5">
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
        </div>

        <nav className="flex shrink-0 items-center gap-1">
          {navLinks.map(({ label, href }) => {
            const active = href !== null && pathname === href;
            const content = (
              <>
                <p
                  className={`text-[15px] leading-[22.5px] whitespace-nowrap ${
                    active ? 'font-semibold' : 'font-normal text-gray-500'
                  }`}
                  style={active ? { color: colors.brand.dark } : undefined}
                >
                  {label}
                </p>
                {active && (
                  <span
                    className="absolute bottom-0 h-0.5 w-3 rounded-full"
                    style={{ backgroundColor: colors.brand.dark }}
                  />
                )}
              </>
            );

            if (href === null) {
              return (
                <div
                  key={label}
                  className="relative flex flex-col items-center justify-center px-4 py-1.5"
                >
                  {content}
                </div>
              );
            }

            return (
              <Link
                key={label}
                href={href}
                className="relative flex flex-col items-center justify-center px-4 py-1.5"
              >
                {content}
              </Link>
            );
          })}
        </nav>

        <Button
          variant="primary"
          className={`${outfit.className} shrink-0`}
          style={{ padding: '8px 20px' }}
        >
          공실 분석 시작하기
        </Button>
      </div>
    </header>
  );
}
