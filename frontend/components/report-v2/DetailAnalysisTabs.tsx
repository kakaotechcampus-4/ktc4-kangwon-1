import { Outfit } from 'next/font/google';
import Tabs, { type TabItem } from '@/components/ui/Tabs';
import FootTrafficChart from '@/components/report/FootTrafficChart';
import CompetitorChart from '@/components/report/CompetitorChart';
import OpenCloseChart from '@/components/report/OpenCloseChart';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

// FootTrafficChart는 자체적으로 좌우/상단 여백(px-8 pt-8)을 갖고 있어 그대로 배치한다.
// CompetitorChart·OpenCloseChart는 기존 페이지에서 두 컴포넌트를 한 행에 나란히 두고
// 그 부모 요소가 여백을 줬던 구조라, 탭 안에 단독으로 둘 때는 동일한 여백을 여기서 감싸준다.
const tabs: TabItem[] = [
  {
    id: 'foot-traffic',
    label: '유동인구',
    content: <FootTrafficChart />,
  },
  {
    id: 'competitors',
    label: '경쟁업체',
    content: (
      <div className="w-full px-8 py-8">
        <CompetitorChart />
      </div>
    ),
  },
  {
    id: 'open-close',
    label: '개폐업 추이',
    content: (
      <div className="w-full px-8 py-8">
        <OpenCloseChart />
      </div>
    ),
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
