import { colors } from '@/styles/tokens';
import type { BuildingField, BuildingInfo } from '@/lib/api/building';
import AddressBanner from '@/components/building-confirm/AddressBanner';
import { formatArea } from './labels';

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
      <AddressBanner
        title={title}
        subtitle={registryLine ? `건축물대장: ${registryLine}` : undefined}
        floorLabel={building.floorLabel}
        tag="건축물대장 HUB"
        note={building.sourceNote}
      />

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
