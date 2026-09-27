import { Outfit } from 'next/font/google';
import Tabs, { type TabItem } from '@/components/ui/Tabs';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import { colors } from '@/styles/tokens';
import type {
  BusinessLifecycleData,
  CommercialAreaData,
  FloatingPopulationData,
} from '@/lib/mockData/report';
import type { IndustryAssessment } from '@/lib/api/types';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

/**
 * 오케스트레이터에 아직 안 붙은 에이전트(source_analyses에서 agent_id를
 * 못 찾은 경우)일 때 탭 내용 대신 보여주는 안내문. 페이지 전체가 깨지지
 * 않도록 해당 탭만 이 문구로 대체한다.
 */
function UnavailableNote({ message }: { message: string }) {
  return (
    <div className="flex w-full items-center justify-center px-8 py-16">
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

type SectionProps<T> = {
  data?: T;
  unavailable?: boolean;
};

/**
 * 경쟁업체 탭은 상권 데이터(data) 외에 추천·비추천 업종 목록도 필요하다
 * — "업종별 경쟁 지표" 카드가 그 업종들을 기준으로 그려지기 때문.
 * 나머지 두 탭과 같은 { data, unavailable } 구조를 유지하면서 두 필드만
 * 덧붙인다.
 */
type CompetitorSectionProps = SectionProps<CommercialAreaData> & {
  recommendations?: IndustryAssessment[];
  notRecommended?: IndustryAssessment[];
};

// FloatingPopulationSection, CompetitorAnalysisSection, OpenCloseTrendSection
// 모두 자체적으로 좌우/상하 여백을 갖고 있어 별도 래퍼 없이 그대로 배치한다.
export default function DetailAnalysisTabs({
  floatingPopulation,
  competitor,
  openClose,
}: {
  floatingPopulation?: SectionProps<FloatingPopulationData>;
  competitor?: CompetitorSectionProps;
  openClose?: SectionProps<BusinessLifecycleData>;
}) {
  const tabs: TabItem[] = [
    {
      id: 'foot-traffic',
      label: '유동인구',
      content: floatingPopulation?.unavailable ? (
        <UnavailableNote message="유동인구 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <FloatingPopulationSection data={floatingPopulation?.data} />
      ),
    },
    {
      id: 'competitors',
      label: '경쟁업체',
      content: competitor?.unavailable ? (
        <UnavailableNote message="경쟁업체 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <CompetitorAnalysisSection
          data={competitor?.data}
          recommendations={competitor?.recommendations}
          notRecommended={competitor?.notRecommended}
        />
      ),
    },
    {
      id: 'open-close',
      label: '개폐업 추이',
      content: openClose?.unavailable ? (
        <UnavailableNote message="개폐업 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <OpenCloseTrendSection data={openClose?.data} />
      ),
    },
  ];

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
