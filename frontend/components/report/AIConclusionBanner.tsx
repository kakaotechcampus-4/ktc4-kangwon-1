import Image from 'next/image';
import { Outfit, DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700', '800'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

export default function AIConclusionBanner() {
  const { industry, reason } = mockReportData.aiConclusion;

  return (
    <div className="w-full px-8 pt-8">
      <div
        className="flex w-full items-center justify-between rounded-xl p-8"
        style={{ backgroundColor: colors.brand.dark }}
      >
        <div className="flex flex-1 flex-col items-start">
          <p
            className={`${dmMono.className} text-xs tracking-[1.68px] uppercase`}
            style={{ color: colors.brand.primary }}
          >
            AI 핵심 결론
          </p>
          <p
            className={`${outfit.className} pt-3 text-[27px] font-bold text-white`}
          >
            이 공실에 가장 적합한 업종은{' '}
            <span
              className={`${outfit.className} text-[32px] font-extrabold`}
              style={{ color: colors.brand.primary }}
            >
              {industry}
            </span>{' '}
            업종입니다.
          </p>
          <p className="max-w-3xl pt-3 text-sm text-white/60">{reason}</p>
        </div>

        <div className="relative size-24 shrink-0 opacity-[0.92]">
          <Image
            src="/images/report/icon-nail-beauty.svg"
            alt=""
            width={96}
            height={96}
          />
        </div>
      </div>
    </div>
  );
}
