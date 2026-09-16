import Link from 'next/link';
import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

/*
 * components/report/ReportHeader.tsx(v1 · v2 공용이던 원본)를 그대로 복제한
 * report-v2 전용 헤더다. components/report/*.tsx는 v1 리포트와 공유하는
 * 파일이라 이 세션 내내 지켜온 "절대 수정 금지" 원칙 때문에 원본을 직접
 * 고치지 않고, report-v2에서만 이 사본으로 바꿔 끼운다(app/report/page.tsx는
 * 여전히 원본 ReportHeader를 그대로 쓴다).
 *
 * 1차 MVP 공실 입력 폼은 "도로명 주소"와 "층/호수"만 받는다. 월세·보증금·
 * 관리비·공실 기간·주차 가능 여부·전용면적·전면폭은 사용자가 입력한 적이
 * 없는데 기존 컴포넌트가 실제 값처럼 하드코딩해 보여주고 있어, 폼이 받는
 * 값(층수)만 실제로 표시하고 나머지는 "미입력"으로 바꿨다. 카드 7개
 * 레이아웃(그리드 컬럼 수, 카드 자체)은 그대로 두고 값 표시 방식만 바꿨다.
 */

const outfit = Outfit({
  subsets: ['latin'],
  // 700은 실제 값(굵게), 400은 "미입력"(가늘게)에 쓴다. next/font는 여기서
  // 선언한 굵기만 로드하므로, 얇은 쪽을 실제로 보여주려면 400도 함께
  // 선언해야 한다(원본 ReportHeader.tsx는 700만 쓰므로 그대로 둔다).
  weight: ['400', '700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type InfoItem = {
  id: string;
  label: string;
  value: string;
  filled: boolean; // 1차 MVP 폼이 실제로 받는 값인지. false면 "미입력"으로 표시한다.
  highlight?: boolean; // filled일 때만 의미가 있다(빈 값을 강조색으로 보여주면 혼란스럽다).
};

const infoItems: InfoItem[] = [
  { id: 'rent', label: '월세', value: '', filled: false },
  { id: 'deposit', label: '보증금', value: '', filled: false },
  { id: 'maintenance', label: '관리비', value: '', filled: false },
  { id: 'vacancy', label: '공실 기간', value: '', filled: false },
  { id: 'parking', label: '주차', value: '', filled: false },
  { id: 'floor', label: '층수', value: mockReportData.floor, filled: true },
  { id: 'area', label: '전용면적', value: '', filled: false },
];

export default function ReportHeaderV2() {
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
          {/*
            원본은 이 줄에 "2층 · 전용 26평 · 전면폭 7.4m"를 전부 표시했다.
            전용면적·전면폭은 MVP 폼이 안 받는 값이라, 부제 줄 같은 한 줄
            요약 자리에 "미입력"을 두 번 나열하면 오히려 번잡해 보여서
            (아래 stat 카드에 이미 각각 "미입력"으로 명확히 표시된다),
            실제로 입력받는 "층수"만 남기기로 했다.
          */}
          <p className={`${dmMono.className} pt-1 text-sm text-gray-500`}>
            {mockReportData.floor}
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
        {infoItems.map(({ id, label, value, filled, highlight }, index) => (
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
              className={`${outfit.className} pt-1.5 text-lg ${filled ? 'font-bold' : 'font-normal'}`}
              style={{
                color: filled
                  ? highlight
                    ? colors.brand.dark
                    : colors.neutral.black
                  : 'var(--color-gray-400)',
              }}
            >
              {filled ? value : '미입력'}
            </p>
          </div>
        ))}
      </Card>
    </div>
  );
}
