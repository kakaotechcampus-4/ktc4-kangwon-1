import Header from '@/components/layout/Header';
import Hero from '@/components/landing/Hero';
import StatsRow from '@/components/landing/StatsRow';
import ProblemCards from '@/components/landing/ProblemCards';
import ValueSteps from '@/components/landing/ValueSteps';
import ReportPreview from '@/components/landing/ReportPreview';
import CTABanner from '@/components/landing/CTABanner';
import { colors } from '@/styles/tokens';

export default function Home() {
  return (
    <div
      className="flex flex-1 flex-col font-sans"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <Hero />
      <StatsRow />
      <ProblemCards />
      <ValueSteps />
      <ReportPreview />
      <CTABanner />
    </div>
  );
}
