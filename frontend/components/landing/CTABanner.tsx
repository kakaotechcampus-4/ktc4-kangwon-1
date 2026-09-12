'use client';

import { useRouter } from 'next/navigation';
import { Outfit } from 'next/font/google';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

export default function CTABanner() {
  const router = useRouter();

  const handleStartAnalysis = () => {
    router.push('/vacancy-input');
  };

  return (
    <div
      className="flex w-full flex-col items-center py-16"
      style={{
        backgroundColor: colors.neutral.white,
        borderTop: `1px solid ${colors.neutral.border}`,
      }}
    >
      <div className="cta-row flex w-full max-w-[1440px] items-center justify-between px-[100px]">
        <div className="flex flex-col items-start">
          <h2
            className={`cta-title ${outfit.className} text-[44px] leading-[50px] font-bold`}
            style={{ color: colors.neutral.black }}
          >
            지금 바로 공실을 분석해보세요.
          </h2>
          <p className="cta-subtitle pt-1 text-[15px] text-gray-600">
            도면과 임대 조건만 입력하면 AI가 업종 적합도를 분석합니다.
          </p>
        </div>

        <Button
          type="button"
          variant="primary"
          className={`cta-button ${outfit.className}`}
          style={{ padding: '16px 32px' }}
          onClick={handleStartAnalysis}
        >
          공실 분석 시작하기 →
        </Button>
      </div>

      {/*
        1024px 미만 전용 축소 처리. 1024px 이상 구간(기존 px-[100px]/text-[44px]/
        leading-[50px]/text-[15px]/버튼 padding 등 className·inline style)은 절대
        건드리지 않고, 아래 @media (max-width: 1023.98px) 블록에서만 !important로
        덮어써 좌측 텍스트 + 우측 버튼 가로 배치는 유지한 채 컨테이너 padding·
        타이틀/서브텍스트 폰트·버튼 크기를 함께 줄인다.

        cta-button은 Button 컴포넌트 내부에서 렌더링되는 <button> 엘리먼트라 scoped
        <style jsx>로는 룰이 전혀 매칭되지 않아(ProblemCards.tsx의 Card/Badge와 동일한
        문제) global로 선언한다. 클래스명이 이 파일에서만 쓰이는 것을 확인했으므로
        다른 컴포넌트와 충돌하지 않는다.

        모든 값은 vw=900px~1024px 구간에서 "MIN + (MAX-MIN) * (100vw-900px)/124"
        형태로 선형 보간해 1024px 지점에서 기존 값과 정확히 일치하고(경계에서 끊기지
        않음), 900px 지점에서 축소된 값에 도달한다.
      */}
      <style jsx global>{`
        @media (max-width: 1023.98px) {
          .cta-row {
            padding-inline: clamp(
              40px,
              calc(40px + (100vw - 900px) * 0.48387),
              100px
            ) !important;
          }

          .cta-title {
            font-size: clamp(
              26px,
              calc(26px + (100vw - 900px) * 0.14516),
              44px
            ) !important;
            line-height: clamp(
              32px,
              calc(32px + (100vw - 900px) * 0.14516),
              50px
            ) !important;
          }

          .cta-subtitle {
            font-size: clamp(
              12px,
              calc(12px + (100vw - 900px) * 0.02419),
              15px
            ) !important;
          }

          .cta-button {
            font-size: clamp(
              12px,
              calc(12px + (100vw - 900px) * 0.01613),
              14px
            ) !important;
            padding: clamp(
                10px,
                calc(10px + (100vw - 900px) * 0.04839),
                16px
              )
              clamp(18px, calc(18px + (100vw - 900px) * 0.1129), 32px) !important;
          }
        }
      `}</style>
    </div>
  );
}
