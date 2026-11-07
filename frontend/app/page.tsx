import { preload } from 'react-dom';
import Header from '@/components/layout/Header';
import { PRETENDARD_HERO_URL } from '@/styles/fonts';
import Hero from '@/components/landing/Hero';
import TwoViews from '@/components/landing/TwoViews';
import ReportPreview from '@/components/landing/ReportPreview';
import Testimonials from '@/components/landing/Testimonials';
import CTABanner from '@/components/landing/CTABanner';

export default function Home() {
  // 히어로 글자 묶음을 미리 받아 CHUM.AI 인트로가 바로 시작되게 한다(Hero.tsx 시작 신호).
  preload(PRETENDARD_HERO_URL, {
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  });
  return (
    <div className="relative flex flex-1 flex-col bg-white">
      <Header overlay />
      <Hero />
      <TwoViews />
      {/*
        첫 화면 밖 섹션은 화면에 다가올 때까지 스타일·레이아웃·페인트를 미룬다.
        첫 로딩 때 히어로 애니메이션과 겹치는 작업을 줄이기 위해서다.
        크기 추정값은 모바일·데스크톱 실제 높이에 맞췄고, 한 번 그려지면 그 크기를 기억한다.
      */}
      <div className="lazy-section [contain-intrinsic-size:auto_1030px] sm:[contain-intrinsic-size:auto_1110px]">
        <ReportPreview />
      </div>
      <div className="lazy-section [contain-intrinsic-size:auto_565px] sm:[contain-intrinsic-size:auto_595px]">
        <Testimonials />
      </div>
      <div className="lazy-section [contain-intrinsic-size:auto_300px] sm:[contain-intrinsic-size:auto_525px]">
        <CTABanner />
      </div>
    </div>
  );
}
