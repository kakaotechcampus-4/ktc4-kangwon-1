import Header from '@/components/layout/Header';
import Hero from '@/components/landing/Hero';
import ServiceSection from '@/components/landing/ServiceSection';
import HowItWorks from '@/components/landing/HowItWorks';
import CTABanner from '@/components/landing/CTABanner';

export default function Home() {
  return (
    <div className="relative flex flex-1 flex-col bg-white">
      <Header overlay />
      <Hero />
      <ServiceSection />
      <HowItWorks />
      <CTABanner />
      <footer className="w-full border-t border-[#EEF1F4] px-4 py-10 sm:px-8">
        <div className="mx-auto flex max-w-[1280px] flex-wrap justify-between gap-4 text-sm text-[#5B6470]">
          <p>
            <span className="font-extrabold text-[#111827]">채움</span> ·
            chum.ai — 카카오테크캠퍼스 4기 강원 1팀
          </p>
        </div>
      </footer>
    </div>
  );
}
