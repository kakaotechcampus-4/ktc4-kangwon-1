import Header from '@/components/layout/Header';
import Hero from '@/components/landing/Hero';
import TwoViews from '@/components/landing/TwoViews';
import ReportPreview from '@/components/landing/ReportPreview';
import Testimonials from '@/components/landing/Testimonials';
import CTABanner from '@/components/landing/CTABanner';

export default function Home() {
  return (
    <div className="relative flex flex-1 flex-col bg-white">
      <Header overlay />
      <Hero />
      <TwoViews />
      <ReportPreview />
      <Testimonials />
      <CTABanner />
      <footer className="w-full border-t border-[#EEF1F4] px-4 py-10 sm:px-8">
        <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-3 text-sm text-[#5B6470]">
          <p className="font-extrabold text-[#111827]">채움 · chum.ai</p>
          <p>공간의 다음 가능성을 찾습니다. © 2026 chum.ai</p>
        </div>
      </footer>
    </div>
  );
}
