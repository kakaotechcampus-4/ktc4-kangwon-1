'use client';

import { Fragment } from 'react';
import { Outfit, DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['300', '400'],
});

type Step = {
  id: string;
  number: string;
  title: string;
  description: string;
};

const steps: Step[] = [
  {
    id: 'space-analysis',
    number: '01',
    title: '공간 분석',
    description:
      '도면과 건물 조건을 분석해 실제 활용 가능한 공간 구조와 제약 조건을 파악합니다.',
  },
  {
    id: 'market-analysis',
    number: '02',
    title: '상권 분석',
    description:
      '반경 500m의 유동인구, 경쟁 점포, 주거·직장 인구 구성을 AI가 종합 분석합니다.',
  },
  {
    id: 'category-recommendation',
    number: '03',
    title: '업종 추천',
    description:
      '공간과 상권 데이터를 결합해 적합·비적합 업종과 정량적 적합도 점수를 제시합니다.',
  },
];

export default function ValueSteps() {
  return (
    <div
      className="flex w-full flex-col items-center py-16"
      style={{ backgroundColor: colors.neutral.black }}
    >
      <div className="value-steps-container flex w-full max-w-[1440px] flex-col items-start">
        <h2
          className={`value-steps-headline ${outfit.className} font-bold text-white`}
        >
          채움은 이렇게 가치를 채웁니다
        </h2>

        <div className="value-steps-row flex w-full items-stretch pt-12">
          {steps.map((step, index) => (
            <Fragment key={step.id}>
              <div className="flex flex-1 flex-col items-start pt-1">
                <div className="flex items-baseline gap-3">
                  <p
                    className={`value-steps-number ${dmMono.className} font-light tracking-[-0.96px] text-white/20`}
                  >
                    {step.number}
                  </p>
                  <p
                    className={`value-steps-title ${outfit.className} font-bold`}
                    style={{ color: colors.brand.primary }}
                  >
                    {step.title}
                  </p>
                </div>
                <div
                  className="mt-5 mb-5 h-px w-8 opacity-50"
                  style={{ backgroundColor: colors.brand.primary }}
                />
                <p className="value-steps-desc w-full text-gray-300">
                  {step.description}
                </p>
              </div>

              {index < steps.length - 1 && (
                <div className="value-steps-divider relative flex w-px shrink-0 items-center justify-center">
                  <div className="absolute inset-0 w-px bg-white/10" />
                  <p
                    className={`value-steps-arrow ${dmMono.className} relative`}
                    style={{
                      backgroundColor: colors.neutral.black,
                      color: colors.brand.primary,
                    }}
                  >
                    →
                  </p>
                </div>
              )}
            </Fragment>
          ))}
        </div>
      </div>

      {/*
        ProblemCards.tsx / 이 파일의 헤드라인에 이미 쓴 것과 동일한 앵커
        (375px→1337px, 계수 divisor=962)를 그대로 재사용해 페이지 전체의
        축소 비율감을 통일한다. 각 스텝 컬럼은 원래도 flex-1이라 폭 자체는
        유동적이었지만, 내부 padding/gap/폰트 크기와 설명 문단의 고정폭
        (기존 w-[287px])이 반응형이 아니어서 좁은 화면에서 넘쳤다. 전부
        이 블록 하나로 옮기고 Tailwind 쪽 고정 클래스(px-[100px],
        gap-[60px], text-[30px] 등)는 제거해 같은 속성을 두 곳에서 동시에
        지정하는 충돌 가능성을 없앤다.
      */}
      <style jsx global>{`
        .value-steps-container {
          padding-inline: clamp(
            20px,
            calc(20px + (100vw - 375px) * 0.0832),
            100px
          );
        }
        .value-steps-headline {
          --headline-fs: clamp(
            26px,
            calc(26px + (100vw - 375px) * 0.018711),
            44px
          );
          font-size: var(--headline-fs);
          line-height: calc(var(--headline-fs) * 1.13636);
        }
        .value-steps-row {
          gap: clamp(16px, calc(16px + (100vw - 375px) * 0.04574), 60px);
        }
        .value-steps-number {
          font-size: clamp(
            24px,
            calc(24px + (100vw - 375px) * 0.02495),
            48px
          );
        }
        .value-steps-title {
          font-size: clamp(
            18px,
            calc(18px + (100vw - 375px) * 0.01247),
            30px
          );
        }
        .value-steps-desc {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.00416),
            15px
          );
          line-height: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.00883),
            24.5px
          );
        }
        .value-steps-arrow {
          font-size: clamp(
            12px,
            calc(12px + (100vw - 375px) * 0.00624),
            18px
          );
          padding-inline: clamp(
            8px,
            calc(8px + (100vw - 375px) * 0.00832),
            16px
          );
        }
      `}</style>
    </div>
  );
}