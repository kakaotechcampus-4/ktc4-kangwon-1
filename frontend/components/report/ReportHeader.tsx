import Link from 'next/link';
import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type InfoItem = {
  id: string;
  label: string;
  value: string;
  highlight?: boolean;
};

const infoItems: InfoItem[] = [
  {
    id: 'rent',
    label: '월세',
    value: mockReportData.rent.replace('월세 ', ''),
  },
  { id: 'deposit', label: '보증금', value: '1,000만원' },
  { id: 'maintenance', label: '관리비', value: '8만원/월' },
  { id: 'vacancy', label: '공실 기간', value: '4개월', highlight: true },
  { id: 'parking', label: '주차', value: '불가' },
  { id: 'floor', label: '층수', value: mockReportData.floor },
  {
    id: 'area',
    label: '전용면적',
    value: mockReportData.area.replace('전용 ', ''),
    highlight: true,
  },
];

export default function ReportHeader() {
  return (
    <div className="flex w-full flex-col items-start px-8 pt-10">
      <Link
        href="/"
        className={`${dmMono.className} text-sm`}
        style={{ color: colors.neutral.black }}
      >
        ← 리포트 목록으로
      </Link>

      <div className="flex w-full items-start justify-between pt-8">
        <div className="flex flex-col items-start">
          <p
            className={`${dmMono.className} text-xs tracking-[1.68px] uppercase`}
            style={{ color: colors.brand.primary }}
          >
            분석 기준일 {mockReportData.analyzedDate}
          </p>
          <h1
            className={`${outfit.className} pt-2 text-[34px] font-bold`}
            style={{ color: colors.neutral.black }}
          >
            {mockReportData.address}
          </h1>
          <p className={`${dmMono.className} pt-1 text-sm text-gray-500`}>
            {mockReportData.floor} · {mockReportData.area} · 전면폭 7.4m
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '8px 16px' }}
          >
            ↓ 리포트 다운로드
          </Button>
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '8px 16px' }}
          >
            ⤴ 공유
          </Button>
        </div>
      </div>

      <Card
        className="mt-8 w-full"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
          padding: 0,
          borderRadius: '12px',
          borderWidth: '1px',
          boxShadow: 'none',
        }}
      >
        {infoItems.map(({ id, label, value, highlight }, index) => (
          <div
            key={id}
            className="flex flex-col items-start px-5 py-4"
            style={
              index > 0
                ? { borderLeft: `1px solid ${colors.neutral.border}` }
                : undefined
            }
          >
            <p
              className={`${dmMono.className} text-[13px] tracking-[2.1px] text-gray-400 uppercase`}
            >
              {label}
            </p>
            <p
              className={`${outfit.className} pt-1.5 text-lg font-bold`}
              style={{
                color: highlight ? colors.brand.dark : colors.neutral.black,
              }}
            >
              {value}
            </p>
          </div>
        ))}
      </Card>
    </div>
  );
}
