import { Outfit } from 'next/font/google';
import Card from '@/components/ui/Card';
import GroupedBar from '@/components/charts/GroupedBar';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const legendItems = [
  { id: 'opened', label: '신규 개업', color: colors.status.recommend },
  { id: 'closed', label: '폐업', color: colors.status.notRecommend },
];

export default function OpenCloseChart() {
  const { openClose, averageCloseRate, openCloseSource } = mockReportData;

  const data = openClose.map((quarter) => ({
    label: quarter.quarter,
    opened: quarter.opened,
    closed: quarter.closed,
  }));

  const series = [
    { key: 'opened', color: colors.status.recommend },
    { key: 'closed', color: colors.status.notRecommend },
  ];

  return (
    <Card
      className="flex-1"
      style={{
        padding: '28px 32px',
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow: 'none',
      }}
    >
      <div className="flex w-full items-center justify-between">
        <h2
          className={`${outfit.className} text-[25px] font-bold`}
          style={{ color: colors.neutral.black }}
        >
          유사업종(뷰티·네일) 개폐업 추이
        </h2>
        <p className="text-sm" style={{ color: colors.status.notRecommend }}>
          평균 폐업률 {averageCloseRate}%
        </p>
      </div>

      <div className="mt-5 flex items-center gap-5">
        {legendItems.map((item) => (
          <div key={item.id} className="flex items-center gap-1.5">
            <span
              className="size-2 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <p className="text-xs text-gray-500">{item.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <GroupedBar data={data} series={series} height={260} />
      </div>

      <p className="mt-2 text-xs text-gray-400">출처: {openCloseSource}</p>
    </Card>
  );
}
