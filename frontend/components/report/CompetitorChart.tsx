import { Outfit } from 'next/font/google';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import VerticalBar from '@/components/charts/VerticalBar';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

export default function CompetitorChart() {
  const { competitors, competitorSource } = mockReportData;

  const items = competitors.map((competitor) => ({
    label: competitor.industry,
    value: competitor.count,
    color: competitor.recommended
      ? colors.status.recommend
      : colors.status.notRecommend,
  }));

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
          업종별 경쟁업체 개수 (반경 500m)
        </h2>
        <p className="text-sm text-gray-500">적을수록 유리</p>
      </div>

      <div
        className="mt-7 grid w-full"
        style={{
          gridTemplateColumns: `repeat(${competitors.length}, minmax(0, 1fr))`,
        }}
      >
        {competitors.map((competitor) => (
          <div
            key={competitor.industry}
            className="flex items-center justify-center"
          >
            <Badge
              style={{
                backgroundColor: competitor.recommended
                  ? colors.status.recommend
                  : colors.status.notRecommend,
                color: colors.neutral.white,
                fontFamily: 'inherit',
                textTransform: 'none',
                letterSpacing: 'normal',
                fontSize: '11px',
                fontWeight: 700,
                borderRadius: '10px',
              }}
            >
              {competitor.recommended ? '추천' : '비추천'}
            </Badge>
          </div>
        ))}
      </div>

      <VerticalBar items={items} height={260} valueSuffix="개" />

      <p className="mt-2 text-xs text-gray-400">출처: {competitorSource}</p>
    </Card>
  );
}
