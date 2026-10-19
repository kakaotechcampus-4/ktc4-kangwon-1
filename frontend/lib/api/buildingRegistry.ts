import type {
  BuildingField,
  BuildingInfo,
  LookupId,
  NeighborhoodFacility,
  ParkingAvailability,
  SewageTreatment,
} from './building';

export function registryField<T>(value: T | null): BuildingField<T> {
  return value === null
    ? { value: null, registryValue: null, source: 'missing' }
    : { value, registryValue: value, source: 'registry' };
}

// 건물 주용도 문자열에서 근린생활시설 종류를 읽는다.
export function facilityFromMainUse(
  mainUse: string | null
): NeighborhoodFacility | null {
  if (mainUse === null) {
    return null;
  }
  if (mainUse.includes('제1종근린생활시설')) {
    return 'type1';
  }
  if (mainUse.includes('제2종근린생활시설')) {
    return 'type2';
  }
  return 'none';
}

type RegistryTitle = {
  dong_name: string | null;
  building_name: string | null;
  main_use: string | null;
  ground_floors: number | null;
  underground_floors: number | null;
  total_area_m2: number | null;
  parking_spaces: number | null;
};

type RegistryRow = {
  dong_name: string | null;
  floor: string | null;
  use: string | null;
  use_detail: string | null;
  area_m2: number | null;
};

type RegistryUnit = RegistryRow & { unit_name: string | null };

type RegistrySewage = {
  method: SewageTreatment | null;
  method_name: string | null;
};

export type BuildingRegistryResponse = {
  road_address: string | null;
  jibun_address: string | null;
  titles: RegistryTitle[] | null;
  floors: RegistryRow[] | null;
  units: RegistryUnit[] | null;
  sewage: RegistrySewage[] | null;
};

export const REGISTRY_SECTIONS: Record<
  LookupId,
  'titles' | 'floors' | 'units' | 'sewage'
> = {
  title: 'titles',
  floor: 'floors',
  exclusiveArea: 'units',
  sewage: 'sewage',
};

export const ADDRESS_ERROR_NOTE = '주소를 확인해 주세요.';
export const LOOKUP_ERROR_NOTE =
  '건축물대장을 불러오지 못했어요. 직접 입력해 주세요.';

export function normalizeFloor(floorUnit: string): string | null {
  const match = floorUnit.match(/(?:^|\s|동)(지하|지|[Bb])?\s*(\d+)\s*층/);
  if (!match) {
    return null;
  }
  const level = Number(match[2]);
  if (level < 1 || level > 999) {
    return null;
  }
  return match[1] ? `지하 ${level}층` : `${level}층`;
}

function unitFromFloorUnit(floorUnit: string): string | null {
  const match = floorUnit.match(/([A-Za-z]?\d+)\s*호/);
  return match ? `${match[1]}호` : null;
}

function compact(text: string | null): string {
  return (text ?? '').replace(/\s+/g, '');
}

function floorsText(title: RegistryTitle | undefined): string | null {
  if (!title || title.ground_floors === null) {
    return null;
  }
  const below = title.underground_floors
    ? ` · 지하 ${title.underground_floors}층`
    : '';
  return `지상 ${title.ground_floors}층${below}`;
}

export function toBuildingInfo(
  registry: BuildingRegistryResponse,
  roadAddress: string,
  floorUnit: string
): BuildingInfo {
  const title = registry.titles?.[0];
  const floor = normalizeFloor(floorUnit);
  const onFloor = <T extends RegistryRow>(rows: T[] | null): T[] =>
    (rows ?? []).filter(
      (row) =>
        floor !== null &&
        compact(row.floor) === compact(floor) &&
        (!title || row.dong_name === title.dong_name)
    );
  const uses = [
    ...new Set(
      onFloor(registry.floors)
        .map((row) => row.use)
        .filter((use): use is string => Boolean(use))
    ),
  ];
  const units = onFloor(registry.units);
  const unitName = unitFromFloorUnit(floorUnit);
  const unit =
    unitName !== null
      ? units.find((row) => compact(row.unit_name) === compact(unitName))
      : units.length === 1
        ? units[0]
        : undefined;
  const mainUse = title?.main_use ?? null;
  return {
    buildingName: title?.building_name ?? '',
    floorLabel: floor ?? '해당 층',
    address: registry.road_address ?? roadAddress,
    mainUse: registryField(mainUse),
    totalAreaM2: registryField(title?.total_area_m2 ?? null),
    floors: registryField(floorsText(title)),
    floorUse: registryField(uses.length > 0 ? uses.join(' · ') : null),
    exclusiveAreaM2: registryField(unit?.area_m2 ?? null),
    parking: registryField<ParkingAvailability>(
      (title?.parking_spaces ?? 0) >= 1 ? 'possible' : null
    ),
    facility: registryField(facilityFromMainUse(mainUse)),
    sewage: registryField(
      registry.sewage?.find((row) => row.method !== null)?.method ?? null
    ),
  };
}

export function emptyBuildingInfo(
  roadAddress: string,
  floorUnit: string,
  sourceNote: string
): BuildingInfo {
  return {
    buildingName: '',
    floorLabel: normalizeFloor(floorUnit) ?? '해당 층',
    address: roadAddress,
    sourceNote,
    mainUse: registryField<string>(null),
    totalAreaM2: registryField<number>(null),
    floors: registryField<string>(null),
    floorUse: registryField<string>(null),
    exclusiveAreaM2: registryField<number>(null),
    parking: registryField<ParkingAvailability>(null),
    facility: registryField<NeighborhoodFacility>(null),
    sewage: registryField<SewageTreatment>(null),
  };
}
