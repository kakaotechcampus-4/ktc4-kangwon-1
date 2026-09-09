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
      <div className="flex w-full max-w-[1440px] flex-col items-start px-[100px]">
        <h2 className={`${outfit.className} text-[44px] font-bold text-white`}>
          채움은 이렇게 가치를 채웁니다
        </h2>

        <div className="flex w-full items-stretch gap-[60px] pt-12">
          {steps.map((step, index) => (
            <Fragment key={step.id}>
              <div className="flex flex-1 flex-col items-start pt-1">
                <div className="flex items-baseline gap-3">
                  <p
                    className={`${dmMono.className} text-[48px] font-light tracking-[-0.96px] text-white/20`}
                  >
                    {step.number}
                  </p>
                  <p
                    className={`${outfit.className} text-[30px] font-bold`}
                    style={{ color: colors.brand.primary }}
                  >
                    {step.title}
                  </p>
                </div>
                <div
                  className="mt-5 mb-5 h-px w-8 opacity-50"
                  style={{ backgroundColor: colors.brand.primary }}
                />
                <p className="w-[287px] text-[15px] leading-[24.5px] text-gray-300">
                  {step.description}
                </p>
              </div>

              {index < steps.length - 1 && (
                <div className="relative flex w-px shrink-0 items-center justify-center">
                  <div className="absolute inset-0 w-px bg-white/10" />
                  <p
                    className={`${dmMono.className} relative px-4 text-[18px]`}
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
    </div>
  );
}
