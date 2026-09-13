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
      className="flex w-full flex-col items-center px-5 py-12 sm:px-8 lg:py-16"
      style={{
        backgroundColor: colors.neutral.white,
        borderTop: `1px solid ${colors.neutral.border}`,
      }}
    >
      <div className="flex w-full max-w-[1440px] flex-col items-start justify-between gap-6 lg:flex-row lg:items-center lg:px-[100px]">
        <div className="flex flex-col items-start">
          <h2
            className={`${outfit.className} text-[28px] leading-[1.2] font-bold sm:text-[36px] lg:text-[44px] lg:leading-[50px]`}
            style={{ color: colors.neutral.black }}
          >
            지금 바로 공실을 분석해보세요.
          </h2>
          <p className="pt-1 text-[15px] text-gray-600">
            도면과 임대 조건만 입력하면 AI가 업종 적합도를 분석합니다.
          </p>
        </div>

        <Button
          type="button"
          variant="primary"
          className={outfit.className}
          style={{ padding: '16px 32px' }}
          onClick={handleStartAnalysis}
        >
          공실 분석 시작하기 →
        </Button>
      </div>
    </div>
  );
}
