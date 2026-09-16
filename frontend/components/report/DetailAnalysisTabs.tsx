import { Outfit } from 'next/font/google';
import Tabs, { type TabItem } from '@/components/ui/Tabs';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

// FloatingPopulationSection, CompetitorAnalysisSection, OpenCloseTrendSection
// 모두 자체적으로 좌우/상하 여백을 갖고 있어 별도 래퍼 없이 그대로 배치한다.
const tabs: TabItem[] = [
  {
    id: 'foot-traffic',
    label: '유동인구',
    content: <FloatingPopulationSection />,
  },
  {
    id: 'competitors',
    label: '경쟁업체',
    content: <CompetitorAnalysisSection />,
  },
  {
    id: 'open-close',
    label: '개폐업 추이',
    content: <OpenCloseTrendSection />,
  },
];

export default function DetailAnalysisTabs() {
  return (
    <div className="flex w-full flex-col items-start pt-8">
      <div className="flex w-full flex-col items-start px-8">
        <h2
          className={`${outfit.className} text-[25px] font-bold`}
          style={{ color: colors.neutral.black }}
        >
          상세 분석
        </h2>
        <p className="pt-1 text-sm text-gray-500">
          유동인구, 경쟁 밀도, 업종 생존율 데이터를 기반으로 추천 결과의 근거를
          확인하세요.
        </p>
      </div>

      <div className="mt-6 w-full">
        <Tabs items={tabs} />
      </div>
    </div>
  );
}
