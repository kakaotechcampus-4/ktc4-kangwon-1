import { Lightbulb, MapPin, Pencil } from 'lucide-react';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';
import type { AnalysisSummary } from '@/lib/mockData/analysisProgress';

type AnalysisSummaryPanelProps = {
  summary: AnalysisSummary;
  onEdit?: () => void;
};

export default function AnalysisSummaryPanel({
  summary,
  onEdit,
}: AnalysisSummaryPanelProps) {
  const rows: { label: string; value: string }[] = [
    { label: '공실 주소', value: summary.address },
    { label: '층 / 호수', value: summary.floorAndUnit },
    { label: '분석 반경', value: `${summary.radiusM}m` },
    { label: '전용면적', value: summary.exclusiveAreaText },
  ];

  return (
    <div className="flex w-full flex-col gap-5">
      <Card
        className="w-full gap-4"
        style={{
          padding: '22px 24px',
          borderRadius: '12px',
          borderWidth: '1px',
          boxShadow: 'none',
        }}
      >
        <div className="flex w-full items-center justify-between">
          <p
            className="text-[17px] font-bold"
            style={{ color: colors.neutral.black }}
          >
            분석 정보 요약
          </p>
          <button
            type="button"
            // mock 핸들러 — 실제로는 공실 입력 화면으로 돌아가 값을 고치는
            // 동작을 붙일 자리다. 지금은 콘솔 로그로만 남긴다.
            onClick={
              onEdit ?? (() => console.log('[AnalysisSummaryPanel] 수정(mock)'))
            }
            className="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs"
            style={{
              borderColor: colors.neutral.border,
              color: 'var(--color-gray-500)',
            }}
          >
            <Pencil size={12} /> 수정
          </button>
        </div>

        <div
          className="h-px w-full"
          style={{ backgroundColor: colors.neutral.border }}
        />

        <div className="flex w-full flex-col gap-3">
          {rows.map((row) => (
            <div key={row.label} className="flex w-full items-start gap-3">
              <p
                className="w-[88px] shrink-0 text-[13px]"
                style={{ color: 'var(--color-gray-500)' }}
              >
                {row.label}
              </p>
              <p
                className="text-sm font-semibold"
                style={{ color: colors.neutral.black }}
              >
                {row.value}
              </p>
            </div>
          ))}
        </div>
      </Card>

      <MockMap summary={summary} />

      <div
        className="flex items-start gap-3 rounded-xl p-5"
        style={{ backgroundColor: '#FFF8E1' }}
      >
        <div
          className="flex size-8 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: colors.neutral.white }}
        >
          <Lightbulb size={16} style={{ color: colors.accent.orange }} />
        </div>
        <div className="flex flex-col gap-1">
          <p
            className="text-sm font-semibold"
            style={{ color: colors.neutral.black }}
          >
            왜 이 정보를 묻나요?
          </p>
          <p className="text-xs" style={{ color: 'var(--color-gray-500)' }}>
            임대 조건, 시설, 주차 여부 등은 업종 적합도를 판단하는 중요한
            요소예요. 더 정확한 분석을 위해 확인이 필요해요.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * 실제 지도 API 연동 전 자리표시자. 중심 마커 + 반경 원 + 랜드마크 라벨만
 * 보여준다. TODO: 카카오맵/네이버맵 등을 붙일 때 summary.centerLat/Lng와
 * nearbyLandmarks[].lat/lng를 좌표 변환에 그대로 사용하고, 이 절대 위치
 * 배치(top/left 퍼센트)는 지도 SDK가 계산한 픽셀 좌표로 교체한다.
 */
function MockMap({ summary }: { summary: AnalysisSummary }) {
  return (
    <div
      className="relative h-[220px] w-full overflow-hidden rounded-xl"
      style={{ backgroundColor: '#E9EFEA' }}
    >
      <div
        className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2"
        style={{ backgroundColor: '#F5D9A8' }}
      />
      <div
        className="absolute top-1/2 left-1/2 size-[160px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2"
        style={{
          borderColor: colors.brand.primary,
          backgroundColor: `${colors.brand.primary}29`,
        }}
      />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <MapPin
          size={26}
          style={{ color: colors.brand.dark }}
          fill={colors.brand.dark}
        />
      </div>
      <div
        className="absolute top-3 right-3 rounded-md px-2.5 py-1 text-xs font-semibold"
        style={{
          backgroundColor: colors.brand.dark,
          color: colors.neutral.white,
        }}
      >
        분석 반경 {summary.radiusM}m
      </div>
      {summary.nearbyLandmarks.map((landmark, index) => (
        <p
          key={landmark.name}
          className="absolute text-[11px]"
          style={{
            color: 'var(--color-gray-600)',
            ...(index === 0
              ? { left: '16%', top: '28%' }
              : { right: '12%', bottom: '20%' }),
          }}
        >
          {landmark.name}
        </p>
      ))}
    </div>
  );
}
