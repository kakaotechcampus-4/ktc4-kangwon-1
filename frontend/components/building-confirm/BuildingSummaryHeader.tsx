import { pretendard } from '@/styles/fonts';
import { colors } from '@/styles/tokens';
import type { BuildingField, BuildingInfo } from '@/lib/api/building';
import { formatArea } from './labels';

const dmMono = pretendard;

type BuildingSummaryHeaderProps = {
  building: BuildingInfo;
  address: string;
};

/** 확인 카드 상단 — 주소를 한 줄의 정보 위계로 강조하고 조회 출처와 층은 보조 정보로 둔다. */

export default function BuildingSummaryHeader({
  building,
  address,
}: BuildingSummaryHeaderProps) {
  const summary: { label: string; field: BuildingField<string | number> }[] = [
    { label: '건물 주용도', field: building.mainUse },
    { label: '연면적', field: building.totalAreaM2 },
    { label: '층수', field: building.floors },
    { label: `${building.floorLabel} 용도`, field: building.floorUse },
  ];
  const title = address || building.address;
  const registryLine = [
    building.buildingName.trim(),
    building.address.trim() === title.trim() ? '' : building.address.trim(),
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex flex-col">
      <div
        className="flex flex-col items-start gap-3 px-4 py-5 sm:gap-4 sm:px-8 sm:py-7"
        style={{ backgroundColor: colors.brand.dark }}
      >
        <h2
          className="w-full font-bold leading-[1.4] break-keep"
          style={{
            color: colors.neutral.white,
            fontSize: 'clamp(1.25rem, 2vw, 1.875rem)',
            overflowWrap: 'normal',
          }}
        >
          {title}
        </h2>
        {registryLine && (
          <p
            className="text-sm break-keep"
            style={{ color: `${colors.neutral.white}CC` }}
          >
            {`건축물대장: ${registryLine}`}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="rounded-md px-3 py-1.5 text-13 font-semibold"
            style={{
              backgroundColor: `${colors.neutral.white}14`,
              color: `${colors.neutral.white}E6`,
            }}
          >
            {building.floorLabel}
          </span>
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
        {building.sourceNote && (
          <p
            className="text-sm break-keep"
            style={{ color: `${colors.neutral.white}CC` }}
          >
            {building.sourceNote}
          </p>
        )}
      </div>

      <dl
        className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 sm:flex sm:flex-wrap sm:gap-x-12 sm:px-10 sm:py-6"
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
