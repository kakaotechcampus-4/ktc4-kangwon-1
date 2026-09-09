import { Outfit } from 'next/font/google';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

export default function CTABanner() {
  return (
    <div
      className="flex w-full flex-col items-center py-16"
      style={{
        backgroundColor: colors.neutral.white,
        borderTop: `1px solid ${colors.neutral.border}`,
      }}
    >
      <div className="flex w-full max-w-[1440px] items-center justify-between px-[100px]">
        <div className="flex flex-col items-start">
          <h2
            className={`${outfit.className} text-[44px] leading-[50px] font-bold`}
            style={{ color: colors.neutral.black }}
          >
            지금 바로 공실을 분석해보세요.
          </h2>
          <p className="pt-1 text-[15px] text-gray-600">
            도면과 임대 조건만 입력하면 AI가 업종 적합도를 분석합니다.
          </p>
        </div>

        <Button
          variant="primary"
          className={outfit.className}
          style={{ padding: '16px 32px' }}
        >
          공실 분석 시작하기 →
        </Button>
      </div>
    </div>
  );
}
