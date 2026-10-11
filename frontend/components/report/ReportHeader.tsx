import { mockProperty } from '@/lib/mockData/property';
import Link from 'next/link';
import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

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
  filled: boolean;
  highlight?: boolean; // filled일 때만 의미가 있다(빈 값을 강조색으로 보여주면 혼란스럽다).
};

export default function ReportHeader({
  address,
  floorUnit,
  parking,
  exclusiveArea,
  radius,
  facility,
  sewage,
  summaryOnly = false,
}: {
  address?: string;
  floorUnit?: string;
  // 상가 정보 확인 화면에서 확인한 값 — 없으면 "미입력"으로 둔다.
  parking?: string;
  exclusiveArea?: string;
  radius?: string;
  facility?: string;
  sewage?: string;
  summaryOnly?: boolean;
} = {}) {
  const displayAddress = address ?? mockReportData.address;

  // 직접 리포트에 접속한 경우에만 목업 층 정보를 사용한다.
  const isRealData = address !== undefined;
  const floorValue =
    floorUnit ?? (isRealData ? undefined : mockReportData.floor);

  // 층·호수는 정보 표에 표시하므로 주소 제목에서는 중복을 제거합니다.
  const titleAddress =
    floorValue && displayAddress.endsWith(` ${floorValue}`)
      ? displayAddress.slice(0, -(floorValue.length + 1))
      : displayAddress;

  const infoItems: InfoItem[] = [
    {
      id: 'floor',
      label: '층 / 호수',
      value: floorValue ?? '',
      filled: Boolean(floorValue),
    },
    {
      id: 'area',
      label: '전용면적',
      value:
        exclusiveArea ?? (isRealData ? '' : mockProperty.exclusiveAreaText),
      filled: Boolean(exclusiveArea) || !isRealData,
    },
    {
      id: 'parking',
      label: '주차 가능 여부',
      value: parking ?? '모름',
      filled: true,
    },
    {
      id: 'facility',
      label: '근린생활시설',
      value: facility ?? (isRealData ? '' : mockProperty.facility),
      filled: Boolean(facility) || !isRealData,
    },
    {
      id: 'sewage',
      label: '오수정화시설',
      value: sewage ?? (isRealData ? '' : mockProperty.sewage),
      filled: Boolean(sewage) || !isRealData,
    },
  ];

  return (
    <div className="flex w-full flex-col items-start px-8 pt-10">
      {!summaryOnly && (
        <>
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
                className={`${outfit.className} pt-2 text-34 font-bold`}
                style={{ color: colors.neutral.black }}
              >
                {titleAddress}
              </h1>
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
        </>
      )}

      <div
        className={`grid w-full grid-cols-[minmax(0,1fr)_340px] items-stretch gap-6 ${summaryOnly ? '' : 'mt-8'}`}
      >
        <Card
          className="grid w-full grid-cols-6 grid-rows-2 overflow-hidden"
          style={{
            padding: 0,
            borderRadius: '12px',
            borderWidth: '1px',
            boxShadow: 'none',
          }}
        >
          {infoItems.map(({ id, label, value, filled, highlight }, index) => (
            <div
              key={id}
              className={`flex min-w-0 flex-col items-start justify-center px-6 py-4 ${index < 3 ? 'col-span-2' : 'col-span-3'}`}
              style={{
                borderLeft:
                  index === 1 || index === 2 || index === 4
                    ? `1px solid ${colors.neutral.border}`
                    : undefined,
                borderTop:
                  index >= 3 ? `1px solid ${colors.neutral.border}` : undefined,
              }}
            >
              <p
                className={`${dmMono.className} text-base tracking-[1px] text-gray-500`}
              >
                {label}
              </p>
              <p
                className={`${outfit.className} break-words pt-2 text-xl ${filled ? 'font-bold' : 'font-normal'}`}
                style={{
                  color: filled
                    ? highlight
                      ? colors.brand.dark
                      : colors.neutral.black
                    : 'var(--color-gray-400)',
                }}
              >
                {filled ? value : id === 'parking' ? '모름' : '미입력'}
              </p>
            </div>
          ))}
        </Card>
        <div className="flex h-full flex-col">
          <aside
            className="relative flex h-full min-h-[224px] flex-col justify-center overflow-hidden rounded-2xl bg-[#004F54] px-7 py-7 text-white"
            aria-label="사용자가 설정한 분석 범위"
          >
            <svg
              className="pointer-events-none absolute -right-12 -top-8 h-64 w-64 text-white/15"
              viewBox="0 0 240 240"
              fill="none"
              aria-hidden="true"
            >
              <circle
                cx="120"
                cy="120"
                r="105"
                stroke="currentColor"
                strokeDasharray="5 6"
              />
              <circle cx="120" cy="120" r="72" stroke="currentColor" />
              <circle cx="120" cy="120" r="38" stroke="currentColor" />
              <circle cx="120" cy="120" r="6" fill="currentColor" />
              <path d="M120 15v210M15 120h210" stroke="currentColor" />
            </svg>
            <div className="relative">
              <p className="text-base font-semibold text-[#BDECE3]">
                분석 범위
              </p>
              <p className="mt-7 text-sm text-white/80">상가 중심 반경</p>
              <p
                className={`${dmMono.className} mt-1 text-[52px] leading-tight font-medium tracking-tight`}
              >
                {radius ?? (isRealData ? '미입력' : `${mockProperty.radiusM}m`)}
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
