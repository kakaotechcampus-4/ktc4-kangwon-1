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

// 일러스트 원본 크기. 카드 좌표와 글자 크기를 이 기준으로 비율 변환합니다.
const ART_WIDTH = 520;
const ART_HEIGHT = 460;

const pctX = (px: number) => `${((px / ART_WIDTH) * 100).toFixed(3)}%`;
const pctY = (px: number) => `${((px / ART_HEIGHT) * 100).toFixed(3)}%`;

/** 컨테이너 폭에 비례해 줄어들되, 읽을 수 있는 하한을 두는 글자 크기입니다. */
const fs = (px: number) =>
  `clamp(${Math.round(px * 0.7)}px, ${((px / ART_WIDTH) * 100).toFixed(3)}cqw, ${px}px)`;

type InfoCard = {
  id: string;
  box: { top: number; left: number; width: number; height: number };
  dark?: boolean;
  content: ReactNode;
};

const infoCards: InfoCard[] = [
  {
    id: 'area',
    box: { top: 84, left: 7, width: 111, height: 58 },
    content: (
      <>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(8) }}
        >
          전용면적
        </p>
        <p
          className={`${outfit.className} font-bold`}
          style={{ color: colors.brand.dark, fontSize: fs(22) }}
        >
          26평
        </p>
      </>
    ),
  },
  {
    id: 'frontage',
    box: { top: 277, left: 5, width: 113, height: 56 },
    content: (
      <>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(8) }}
        >
          전면폭
        </p>
        <p
          className={`${outfit.className} font-bold`}
          style={{ color: colors.brand.primary, fontSize: fs(22) }}
        >
          7.4m
        </p>
      </>
    ),
  },
  {
    id: 'market',
    box: { top: 79, left: 401, width: 117, height: 71 },
    content: (
      <>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(8) }}
        >
          상권 분석
        </p>
        <p
          className={`${outfit.className} font-bold`}
          style={{ color: colors.brand.dark, fontSize: fs(13) }}
        >
          반경 500m
        </p>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(7) }}
        >
          234개 점포
        </p>
      </>
    ),
  },
  {
    id: 'ai-pick',
    box: { top: 267, left: 403, width: 115, height: 76 },
    dark: true,
    content: (
      <>
        <p
          className={dmMono.className}
          style={{ color: colors.brand.primary, fontSize: fs(8) }}
        >
          AI 추천 1위
        </p>
        <p
          className={`${outfit.className} font-bold text-white`}
          style={{ fontSize: fs(15) }}
        >
          네일·뷰티
        </p>
        <div className="mt-1 flex items-baseline gap-1">
          <p
            className={`${dmMono.className} text-gray-400`}
            style={{ fontSize: fs(9) }}
          >
            적합도
          </p>
          <p
            className={`${outfit.className} font-bold`}
            style={{ color: colors.brand.primary, fontSize: fs(16) }}
          >
            92점
          </p>
        </div>
      </>
    ),
  },
  {
    id: 'foot-traffic',
    box: { top: 381, left: 149, width: 104, height: 39 },
    content: (
      <>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(7) }}
        >
          유동인구
        </p>
        <p
          className={`${outfit.className} font-bold`}
          style={{ color: colors.brand.dark, fontSize: fs(11) }}
        >
          4,820명/일
        </p>
      </>
    ),
  },
  {
    id: 'competitors',
    box: { top: 383, left: 286, width: 93, height: 39 },
    content: (
      <>
        <p
          className={`${dmMono.className} text-gray-400`}
          style={{ fontSize: fs(7) }}
        >
          경쟁점포
        </p>
        <p
          className={`${outfit.className} font-bold`}
          style={{ color: colors.brand.dark, fontSize: fs(11) }}
        >
          1개소
        </p>
      </>
    ),
  },
];

function cardStyle({
  box,
  dark,
}: Pick<InfoCard, 'box' | 'dark'>): CSSProperties {
  return {
    top: pctY(box.top),
    left: pctX(box.left),
    width: pctX(box.width),
    height: pctY(box.height),
    backgroundColor: dark ? colors.brand.dark : colors.neutral.white,
    border: dark ? 'none' : `1px solid ${colors.neutral.border}`,
  };
}

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
      className="flex w-full justify-center px-5 py-12 sm:px-8 lg:py-16"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <div className="flex w-full max-w-[1241px] flex-col items-center gap-12 lg:flex-row lg:items-center lg:justify-between lg:gap-16 xl:gap-[240px]">
        <div className="flex w-full max-w-[481px] flex-col items-start lg:shrink-0">
          <div
            className="flex items-center gap-2 rounded-full px-3 py-1.5"
            style={{ backgroundColor: `${colors.brand.primary}1A` }}
          >
            <span
              className="size-[6px] shrink-0 rounded-full"
              style={{ backgroundColor: colors.brand.primary }}
            />
            <p
              className={`${dmMono.className} text-[10px] whitespace-nowrap sm:text-[12px]`}
              style={{ color: colors.brand.primary }}
            >
              AI PROPTECH · POWERED BY DATA
            </p>
          </div>

          <h1
            className={`${outfit.className} pt-6 text-[40px] leading-[1.15] font-extrabold sm:text-[52px] lg:text-[68px] lg:leading-[69px]`}
            style={{ color: colors.neutral.black }}
          >
            공실에 맞는 업종
            <br />
            <span style={{ color: colors.brand.primary }}>
              AI가 찾아드립니다.
            </span>
          </h1>

          <p className="max-w-[440px] pt-6 text-base leading-[1.6] text-gray-600 sm:text-lg sm:leading-[29.25px]">
            도면·임대조건·상권 데이터를 함께 분석해
            <br className="hidden sm:inline" />내 공간에 가장 적합한 업종을
            추천합니다.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-8">
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

        <div
          className="relative aspect-[520/460] w-full max-w-[520px] lg:shrink-0"
          style={{ containerType: 'inline-size' }}
        >
          <Image
            src="/images/hero-illustration.png"
            alt="공실 건물과 상권 반경을 보여주는 등각투영 일러스트"
            width={1040}
            height={920}
            priority
            sizes="(max-width: 1024px) 100vw, 520px"
            className="h-full w-full object-contain"
          />
          {infoCards.map(({ id, box, dark, content }) => (
            <div
              key={id}
              className="absolute flex flex-col justify-center gap-0.5 rounded-xl px-[2.3cqw] py-[1.5cqw] shadow-[0_4px_12px_rgba(0,0,0,0.08)]"
              style={cardStyle({ box, dark })}
            >
              {content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
