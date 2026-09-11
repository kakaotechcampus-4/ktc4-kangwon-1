import { DM_Mono } from 'next/font/google';
import Header from '@/components/layout/Header';
import ReportHeader from '@/components/report/ReportHeader';
import RecommendationSectionV2 from '@/components/report-v2/RecommendationSectionV2';
import AIAnalysisSummary from '@/components/report-v2/AIAnalysisSummary';
import DetailAnalysisTabs from '@/components/report-v2/DetailAnalysisTabs';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

export default function ReportV2Page() {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <ReportHeader />
      <RecommendationSectionV2 />
      <AIAnalysisSummary />
      <DetailAnalysisTabs />

      <div
        className="mx-8 mt-10 mb-10 flex items-center justify-between pt-6"
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
