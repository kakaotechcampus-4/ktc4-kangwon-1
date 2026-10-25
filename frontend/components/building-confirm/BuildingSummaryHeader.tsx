import { pretendard } from '@/styles/fonts';
import { colors } from '@/styles/tokens';
import type { BuildingField, BuildingInfo } from '@/lib/api/building';
import { formatArea } from './labels';

const dmMono = pretendard;

type BuildingSummaryHeaderProps = {
  building: BuildingInfo;
};

/** 확인 카드 상단 — 다크 헤더(건물명·층, 주소)와 읽기 전용 요약 4칸. */

export default function BuildingSummaryHeader({
  building,
}: BuildingSummaryHeaderProps) {
  const summary: { label: string; field: BuildingField<string | number> }[] = [
    { label: '건물 주용도', field: building.mainUse },
    { label: '연면적', field: building.totalAreaM2 },
    { label: '층수', field: building.floors },
    { label: `${building.floorLabel} 용도`, field: building.floorUse },
  ];

  return (
    <div className="flex flex-col">
      <div
        className="flex flex-col-reverse items-start gap-3 px-5 py-6 sm:flex-row sm:justify-between sm:gap-6 sm:px-10 sm:py-8"
        style={{ backgroundColor: colors.brand.dark }}
      >
        <div className="flex min-w-0 flex-col gap-2">
          <h2
            className="text-fluid-24-30 font-bold break-keep"
            style={{ color: colors.neutral.white }}
          >
            {building.buildingName} {building.floorLabel}
          </h2>
          <p
            className="text-fluid-15-16 break-keep"
            style={{ color: `${colors.neutral.white}CC` }}
          >
            {building.address}
            {building.sourceNote && ` · ${building.sourceNote}`}
          </p>
        </div>
        <span
          className={`${dmMono.className} shrink-0 rounded-md px-3 py-1.5 text-13 tracking-[1px]`}
          style={{
            backgroundColor: `${colors.neutral.white}14`,
            color: '#7F9BDC',
          }}
        >
          건축물대장 HUB
        </span>
      </div>

      <dl
        className="grid grid-cols-2 gap-x-6 gap-y-4 px-5 py-5 sm:flex sm:flex-wrap sm:gap-x-12 sm:px-10 sm:py-6"
        style={{ backgroundColor: `${colors.brand.primary}08` }}
      >
        {summary.map(({ label, field }) => (
          <div key={label} className="flex min-w-0 flex-col gap-1">
            <dt className="text-13" style={{ color: colors.text.tertiary }}>
              {label}
            </dt>
            <dd
              className="text-base font-bold break-keep"
              style={{
                color:
                  field.value === null
                    ? colors.text.tertiary
                    : colors.text.primary,
              }}
            >
              {field.value === null
                ? '확인 안 됨'
                : typeof field.value === 'number'
                  ? formatArea(field.value)
                  : field.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
