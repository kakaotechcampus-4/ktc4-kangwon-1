'use client';

import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { Outfit, DM_Mono } from 'next/font/google';
import type { CSSProperties, ReactNode } from 'react';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700', '800'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

type InfoCard = {
  id: string;
  style: CSSProperties;
  dark?: boolean;
  content: ReactNode;
};

const infoCards: InfoCard[] = [
  {
    id: 'area',
    style: { top: 84, left: 7, width: 111, height: 58 },
    content: (
      <>
        <p className={`${dmMono.className} text-[8px] text-gray-400`}>
          전용면적
        </p>
        <p
          className={`${outfit.className} text-[22px] font-bold`}
          style={{ color: colors.brand.dark }}
        >
          26평
        </p>
      </>
    ),
  },
  {
    id: 'frontage',
    style: { top: 277, left: 5, width: 113, height: 56 },
    content: (
      <>
        <p className={`${dmMono.className} text-[8px] text-gray-400`}>전면폭</p>
        <p
          className={`${outfit.className} text-[22px] font-bold`}
          style={{ color: colors.brand.primary }}
        >
          7.4m
        </p>
      </>
    ),
  },
  {
    id: 'market',
    style: { top: 79, left: 401, width: 117, height: 71 },
    content: (
      <>
        <p className={`${dmMono.className} text-[8px] text-gray-400`}>
          상권 분석
        </p>
        <p
          className={`${outfit.className} text-[13px] font-bold`}
          style={{ color: colors.brand.dark }}
        >
          반경 500m
        </p>
        <p className={`${dmMono.className} text-[7px] text-gray-400`}>
          234개 점포
        </p>
      </>
    ),
  },
  {
    id: 'ai-pick',
    style: { top: 267, left: 403, width: 115, height: 76 },
    dark: true,
    content: (
      <>
        <p
          className={`${dmMono.className} text-[8px]`}
          style={{ color: colors.brand.primary }}
        >
          AI 추천 1위
        </p>
        <p className={`${outfit.className} text-[15px] font-bold text-white`}>
          네일·뷰티
        </p>
        <div className="mt-1 flex items-baseline gap-1">
          <p className={`${dmMono.className} text-[9px] text-gray-400`}>
            적합도
          </p>
          <p
            className={`${outfit.className} text-[16px] font-bold`}
            style={{ color: colors.brand.primary }}
          >
            92점
          </p>
        </div>
      </>
    ),
  },
  {
    id: 'foot-traffic',
    style: { top: 381, left: 149, width: 104, height: 39 },
    content: (
      <>
        <p className={`${dmMono.className} text-[7px] text-gray-400`}>
          유동인구
        </p>
        <p
          className={`${outfit.className} text-[11px] font-bold`}
          style={{ color: colors.brand.dark }}
        >
          4,820명/일
        </p>
      </>
    ),
  },
  {
    id: 'competitors',
    style: { top: 383, left: 286, width: 93, height: 39 },
    content: (
      <>
        <p className={`${dmMono.className} text-[7px] text-gray-400`}>
          경쟁점포
        </p>
        <p
          className={`${outfit.className} text-[11px] font-bold`}
          style={{ color: colors.brand.dark }}
        >
          1개소
        </p>
      </>
    ),
  },
];

export default function Hero() {
  const router = useRouter();

  const handleStartAnalysis = () => {
    router.push('/vacancy-input');
  };

  const handleViewReportPreview = () => {
    document
      .getElementById('report-preview')
      ?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div
      className="flex w-full justify-center py-16"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <div className="flex w-full max-w-[1241px] items-center gap-[240px]">
        <div className="flex w-[481px] shrink-0 flex-col items-start">
          <div
            className="flex items-center gap-2 rounded-full px-3 py-1.5"
            style={{ backgroundColor: `${colors.brand.primary}1A` }}
          >
            <span
              className="size-[6px] shrink-0 rounded-full"
              style={{ backgroundColor: colors.brand.primary }}
            />
            <p
              className={`${dmMono.className} whitespace-nowrap text-[12px]`}
              style={{ color: colors.brand.primary }}
            >
              AI PROPTECH · POWERED BY DATA
            </p>
          </div>

          <h1
            className={`${outfit.className} pt-6 text-[68px] leading-[69px] font-extrabold whitespace-nowrap`}
            style={{ color: colors.neutral.black }}
          >
            공실에 맞는 업종
            <br />
            <span style={{ color: colors.brand.primary }}>
              AI가 찾아드립니다.
            </span>
          </h1>

          <p className="max-w-[440px] pt-6 text-lg leading-[29.25px] text-gray-600">
            도면·임대조건·상권 데이터를 함께 분석해
            <br />내 공간에 가장 적합한 업종을 추천합니다.
          </p>

          <div className="flex items-center gap-3 pt-8">
            <Button
              type="button"
              variant="primary"
              className={outfit.className}
              onClick={handleStartAnalysis}
            >
              공실 분석 시작하기 →
            </Button>
            <Button
              type="button"
              variant="outline"
              className="text-gray-600"
              onClick={handleViewReportPreview}
            >
              리포트 예시 보기
            </Button>
          </div>
        </div>

        <div className="relative h-[460px] w-[520px] shrink-0">
          <Image
            src="/images/hero-illustration.png"
            alt="공실 건물과 상권 반경을 보여주는 등각투영 일러스트"
            width={1040}
            height={920}
            priority
            className="h-full w-full object-contain"
          />
          {infoCards.map(({ id, style, dark, content }) => (
            <div
              key={id}
              className="absolute flex flex-col justify-center gap-0.5 rounded-xl px-3 py-2 shadow-[0_4px_12px_rgba(0,0,0,0.08)]"
              style={{
                ...style,
                backgroundColor: dark
                  ? colors.brand.dark
                  : colors.neutral.white,
                border: dark ? 'none' : `1px solid ${colors.neutral.border}`,
              }}
            >
              {content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
