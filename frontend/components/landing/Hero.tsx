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
      <div className="hero-fluid-row flex w-full max-w-[1440px] flex-col items-start md:flex-row md:items-center md:justify-center">
        <div className="hero-fluid-textcol flex w-full flex-col items-start md:shrink-0">
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
            className={`hero-fluid-title ${outfit.className} pt-6 text-[32px] leading-[38px] font-extrabold`}
            style={{ color: colors.neutral.black }}
          >
            공실에 맞는 업종
            <br />
            <span style={{ color: colors.brand.primary }}>
              AI가 찾아드립니다.
            </span>
          </h1>

          <p className="max-w-[440px] pt-6 text-sm leading-[22px] text-gray-600 md:text-base md:leading-[24px] lg:text-lg lg:leading-[29.25px]">
            도면·임대조건·상권 데이터를 함께 분석해
            <br />내 공간에 가장 적합한 업종을 추천합니다.
          </p>

          <div className="flex w-full flex-col items-start gap-3 pt-8 sm:w-auto sm:flex-row sm:items-center">
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

        <div className="hero-fluid-illustration overflow-hidden md:shrink-0">
          <div className="hero-fluid-illustration-inner relative origin-top-left">
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

      {/*
        모든 반응형 사이즈 값(padding, gap, 컬럼 폭, 폰트, 일러스트 크기)을
        이 블록 하나에서만 관리한다. Tailwind 유틸 클래스(md:w-[...], md:px-8 등)를
        같은 요소/같은 속성에 절대 병행 사용하지 않는다 — 두 스타일 소스가
        동일 속성을 동시에 지정하면 specificity가 같아서 "문서 삽입 순서"에
        따라 승자가 갈리고, Next.js에서는 그 순서가 보장되지 않아 빌드마다
        결과가 달라질 수 있기 때문. 이 파일이 유일한 소스이므로 !important
        없이도 자연스러운 CSS 캐스케이드(나중에 선언된 규칙이 우선)만으로
        1024~1440 구간 fluid 스케일링이 항상 예측 가능하게 동작한다.
      */}
      <style jsx>{`
        .hero-fluid-row {
          padding-inline: 24px;
          gap: 40px;
        }

        /*
          기존 375~1440 단일 공식(327px→587.89px)은 그대로 base 규칙으로
          유지한다 — 1024px 이상 구간은 이 base 값이 그대로 적용되므로
          전혀 변경되지 않는다. 375~1023.98px 구간만 아래 max-width 미디어
          쿼리로 덮어써서, 기존 공식이 1024px 지점에서 내던 값(485.98px)은
          그대로 유지한 채 375px 지점의 시작값만 327px→255px(약 22% 축소)로
          낮추고, 그 사이를 새 기울기로 다시 선형 보간한다. 두 공식이
          1024px 경계에서 정확히 485.98px로 맞물려서 이어지므로 이음매가
          눈에 띄지 않는다.
        */
        .hero-fluid-illustration {
          --hero-illust-w: clamp(
            327px,
            calc(327px + (100vw - 375px) * 0.244967),
            587.89px
          );
          width: var(--hero-illust-w);
          height: auto;
          aspect-ratio: 520 / 460;
        }
        .hero-fluid-illustration-inner {
          width: 520px;
          height: 460px;
          transform: scale(calc(var(--hero-illust-w) / 520px));
        }

        @media (max-width: 1023.98px) {
          .hero-fluid-illustration {
            --hero-illust-w: clamp(
              190px,
              calc(190px + (100vw - 375px) * 0.456055),
              485.98px
            );
            width: var(--hero-illust-w);
            height: auto;
            aspect-ratio: 520 / 460;
          }
        }

        @media (min-width: 768px) {
          .hero-fluid-row {
            padding-inline: 32px;
            gap: 32px;
          }
          .hero-fluid-textcol {
            width: 320px;
          }
          .hero-fluid-title {
            font-size: 36px;
            line-height: 40px;
          }
        }

        @media (min-width: 1024px) {
          .hero-fluid-row {
            padding-inline: clamp(
              32px,
              calc(32px + (100vw - 1024px) * 0.16226),
              99.5px
            );
            gap: clamp(
              71.11px,
              calc(71.11px + (100vw - 1024px) * 0.24279),
              172.11px
            );
          }

          .hero-fluid-textcol {
            width: clamp(
              400px,
              calc(400px + (100vw - 1024px) * 0.19471),
              481px
            );
          }

          .hero-fluid-title {
            font-size: clamp(
              52px,
              calc(52px + (100vw - 1024px) * 0.03846),
              68px
            );
            line-height: clamp(
              53px,
              calc(53px + (100vw - 1024px) * 0.03846),
              69px
            );
            white-space: nowrap;
          }
        }
      `}</style>
    </div>
  );
}