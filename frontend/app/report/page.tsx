import { DM_Mono } from 'next/font/google';
import Header from '@/components/layout/Header';
import ReportHeader from '@/components/report/ReportHeader';
import AIConclusionBanner from '@/components/report/AIConclusionBanner';
import RecommendationSection from '@/components/report/RecommendationSection';
import FootTrafficChart from '@/components/report/FootTrafficChart';
import CompetitorChart from '@/components/report/CompetitorChart';
import OpenCloseChart from '@/components/report/OpenCloseChart';
import AISummaryBanner from '@/components/report/AISummaryBanner';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

export default function ReportPage() {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <ReportHeader />
      <AIConclusionBanner />
      <RecommendationSection />
      <FootTrafficChart />
      <div className="flex w-full items-start gap-6 px-8 pt-8">
        <CompetitorChart />
        <OpenCloseChart />
      </div>
      <AISummaryBanner />

      <div
        className="mx-8 mt-8 mb-10 flex items-center justify-between pt-6"
        style={{ borderTop: `1px solid ${colors.neutral.border}` }}
      >
        <p className={`${dmMono.className} text-xs text-gray-400`}>
          chum.ai · 분석일 {mockReportData.analyzedDate} · 춘천시 후평동 234-5
        </p>
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '10px 16px', fontSize: '12px' }}
          >
            리포트 다운로드 (PDF)
          </Button>
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '10px 16px', fontSize: '12px' }}
          >
            공유 링크 복사
          </Button>
        </div>
      </div>
    </div>
  );
}
