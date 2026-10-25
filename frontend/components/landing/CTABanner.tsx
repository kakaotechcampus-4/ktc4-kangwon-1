import Link from 'next/link';
import { colors } from '@/styles/tokens';

export default function CTABanner() {
  return (
    <section className="w-full px-4 py-26 sm:px-8">
      <div
        className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-8 rounded-[28px] px-8 py-14 sm:px-12 sm:py-16"
        style={{ backgroundColor: colors.brand.primary }}
      >
        <div>
          <h2 className="text-34 leading-[1.35] font-extrabold tracking-[-0.02em] text-white">
            우리 건물 공실,
            <br />
            지금 바로 분석해 보세요
          </h2>
          <p className="mt-3.5 text-base text-[#DCE6FF]">
            주소 하나로 시작하는 공실 리포트
          </p>
        </div>
        <Link
          href="/vacancy-input"
          className="inline-flex h-14 items-center gap-2.5 rounded-xl px-7 text-base font-extrabold text-[#1B2A33] transition-opacity hover:opacity-90"
          style={{ backgroundColor: '#F2B84B' }}
        >
          공실 분석 시작하기
          <svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true">
            <path
              d="M2 7h10M8 3l4 4-4 4"
              stroke="currentColor"
              strokeWidth="1.8"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Link>
      </div>
    </section>
  );
}
