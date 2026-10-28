import Link from 'next/link';
import { MapPin, Pencil } from 'lucide-react';
import { colors } from '@/styles/tokens';
import type { AnalysisSummary } from '@/lib/mockData/analysisProgress';

type AnalysisSummaryPanelProps = {
  summary: AnalysisSummary;
  onEdit?: () => void;
};

/**
 * 우측 보조 영역 — 입력한 공실 정보를 빠르게 되짚어보는 용도라 중앙 질문
 * 영역보다 눈에 덜 띄게 만든다(그림자 없음, 작은 글자, 미니 지도).
 */
export default function AnalysisSummaryPanel({
  summary,
  onEdit,
}: AnalysisSummaryPanelProps) {
  const rows: { label: string; value: string }[] = [
    { label: '주소', value: summary.address },
    { label: '층 / 호수', value: summary.floorAndUnit },
    { label: '전용면적', value: summary.exclusiveAreaText },
    { label: '분석 반경', value: `${summary.radiusM}m` },
  ];

  return (
    <div
      className="flex w-full flex-col gap-4 rounded-3xl shadow-[0_18px_40px_rgba(16,35,58,0.06)] p-5"
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    >
      <div className="flex items-center justify-between">
        <p
          className="text-15 font-semibold"
          style={{ color: colors.text.secondary }}
        >
          분석 대상
        </p>
        {/* onEdit가 없으면 공실 입력 화면으로 돌아간다(입력값은 세션에 남아 있다). */}
        {onEdit ? (
          <button
            type="button"
            onClick={onEdit}
            className="flex items-center gap-1 text-13"
            style={{ color: colors.text.tertiary }}
          >
            <Pencil size={12} /> 수정
          </button>
        ) : (
          <Link
            href="/vacancy-input"
            className="flex items-center gap-1 text-13"
            style={{ color: colors.text.tertiary }}
          >
            <Pencil size={12} /> 수정
          </Link>
        )}
      </div>

      <MiniMap radiusM={summary.radiusM} />

      <dl className="flex flex-col gap-2.5">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start gap-3">
            <dt
              className="w-[68px] shrink-0 text-13 leading-relaxed"
              style={{ color: colors.text.tertiary }}
            >
              {row.label}
            </dt>
            <dd
              className="text-sm leading-relaxed font-medium"
              style={{ color: colors.text.primary }}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * 실제 지도 API 연동 전 자리표시자. 중심 마커 + 반경 원만 보여준다.
 * TODO: 카카오맵/네이버맵 등을 붙일 때 summary.centerLat/Lng로 중심을 잡고,
 * 이 자리를 지도 SDK가 그린 정적 미니 지도로 교체한다.
 */
function MiniMap({ radiusM }: { radiusM: number }) {
  return (
    <div
      className="relative h-[112px] w-full overflow-hidden rounded-lg"
      style={{ backgroundColor: '#E9EFEA' }}
    >
      <div
        className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2"
        style={{ backgroundColor: '#F5D9A8' }}
      />
      <div
        className="absolute top-1/2 left-1/2 size-[84px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px]"
        style={{
          borderColor: colors.brand.primary,
          backgroundColor: `${colors.brand.primary}29`,
        }}
      />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <MapPin
          size={18}
          style={{ color: colors.brand.dark }}
          fill={colors.brand.dark}
        />
      </div>
      <div
        className="absolute right-2 bottom-2 rounded px-2 py-0.5 text-xs font-semibold"
        style={{
          backgroundColor: colors.brand.dark,
          color: colors.neutral.white,
        }}
      >
        반경 {radiusM}m
      </div>
    </div>
  );
}
