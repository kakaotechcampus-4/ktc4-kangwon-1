import { API_BASE_URL } from '@/lib/api/config';
import { MOCK_MODE } from '@/lib/api/mockMode';
/**
 * 상가 정보 확인(/building-confirm) 화면이 쓰는 건축물대장 조회.
 *
 * 건축물대장 HUB 백엔드 API를 호출한다. 프론트 mock 모드에서는 API 계약의
 * `mock=true`로 고정 응답을 받아 화면은 아래 타입과 onStepChange 콜백에만 의존한다.
 *
 * 조회한 값은 분석 요청 본문에 넣지 않는다(백엔드 AnalysisRequest가 정의되지
 * 않은 필드를 거절한다). 확인한 값은 resultStore의 saveConfirmedBuilding으로
 * sessionStorage에만 남긴다.
 */

// registry: 건축물대장 값 그대로 / user: 사용자가 고치거나 채움 / missing: 건축물대장에 없음
export type FieldSource = 'registry' | 'user' | 'missing';

export type BuildingField<T> = {
  value: T | null;
  // 건축물대장 원래 값. 없으면 null — 사용자가 고쳐도 바뀌지 않는다.
  registryValue: T | null;
  source: FieldSource;
};

export type ParkingAvailability = 'possible' | 'impossible' | 'unknown';
export type NeighborhoodFacility = 'type1' | 'type2' | 'none';

export const SEWAGE_OPTIONS = [
  '하수종말처리장 연결',
  '정화조',
  '오수처리시설',
  '모름',
] as const;
export type SewageTreatment = (typeof SEWAGE_OPTIONS)[number];

export type BuildingInfo = {
  buildingName: string;
  floorLabel: string; // "4층"
  address: string;
  // 헤더 주소 옆에 붙는 짧은 메모 (예: mock 데이터 안내)
  sourceNote?: string;
  // 요약(읽기 전용)
  mainUse: BuildingField<string>;
  totalAreaM2: BuildingField<number>;
  floors: BuildingField<string>;
  floorUse: BuildingField<string>;
  // 수정 가능
  exclusiveAreaM2: BuildingField<number>;
  parking: BuildingField<ParkingAvailability>;
  facility: BuildingField<NeighborhoodFacility>;
  sewage: BuildingField<SewageTreatment>;
};

export type LookupId = 'title' | 'floor' | 'exclusiveArea' | 'sewage';
export type LookupStatus = 'pending' | 'loading' | 'done' | 'failed';

// 조회 순서. 화면의 조회 목록도 이 순서를 따른다.
export const LOOKUP_ORDER: LookupId[] = [
  'title',
  'floor',
  'exclusiveArea',
  'sewage',
];

type FetchOptions = {
  // 상태가 바뀔 때마다 호출된다 — 화면이 항목별 진행 상태를 그리는 데 쓴다.
  onStepChange?: (id: LookupId, status: LookupStatus) => void;
  signal?: AbortSignal;
  // 주소와 별도로 입력된 층·호실. 결과의 층별 용도와 전용면적을 고르는 데 쓴다.
  floorUnit?: string;
  // 화면 확인용: 여기 넣은 항목은 일부러 실패시켜 missing 흐름을 볼 수 있다.
  failLookups?: LookupId[];
};

type BuildingRegistryTitle = {
  dong_name: string | null;
  building_name: string | null;
  main_use: string | null;
  ground_floors: number | null;
  underground_floors: number | null;
  total_area_m2: number | null;
  parking_spaces: number | null;
};

type BuildingRegistryFloor = {
  dong_name: string | null;
  floor: string | null;
  use: string | null;
  use_detail: string | null;
  area_m2: number | null;
};

type BuildingRegistryUnit = {
  dong_name: string | null;
  unit_name: string | null;
  floor: string | null;
  use: string | null;
  use_detail: string | null;
  area_m2: number | null;
};

type BuildingRegistrySewage = {
  method: SewageTreatment | null;
  method_name: string | null;
};

type BuildingRegistryResponse = {
  road_address: string | null;
  jibun_address: string | null;
  titles: BuildingRegistryTitle[] | null;
  floors: BuildingRegistryFloor[] | null;
  units: BuildingRegistryUnit[] | null;
  sewage: BuildingRegistrySewage[] | null;
};

export class BuildingRegistryApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'BuildingRegistryApiError';
    this.status = status;
  }
}

export function registryField<T>(value: T | null): BuildingField<T> {
  return value === null
    ? { value: null, registryValue: null, source: 'missing' }
    : { value, registryValue: value, source: 'registry' };
}

// 건물 주용도 문자열에서 근린생활시설 종류를 읽는다.
function facilityFromMainUse(
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

/**
 * 건축물대장 4개 항목을 차례로 조회한다. 한 항목이 실패해도 멈추지 않고,
 * 그 항목에서 오는 필드를 missing으로 채워 돌려준다.
 */
export async function fetchBuildingInfo(
  address: string,
  { onStepChange, signal, floorUnit = '', failLookups = [] }: FetchOptions = {}
): Promise<BuildingInfo> {
  return fetchRegistryBuildingInfo(
    address,
    floorUnit,
    onStepChange,
    signal,
    failLookups
  );
}

async function fetchRegistryBuildingInfo(
  address: string,
  floorUnit: string,
  onStepChange?: FetchOptions['onStepChange'],
  signal?: AbortSignal,
  failLookups: LookupId[] = []
): Promise<BuildingInfo> {
  const requestedAddress = [address, floorUnit.trim()]
    .filter(Boolean)
    .join(' ');
  const query = new URLSearchParams({
    address: requestedAddress,
    mock: String(MOCK_MODE),
  });
  const lookupIds: LookupId[] = ['title', 'floor', 'exclusiveArea', 'sewage'];

  lookupIds.forEach((id) => onStepChange?.(id, 'loading'));

  let response: Response;
  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/building-registry?${query.toString()}`,
      { signal }
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }
    lookupIds.forEach((id) => onStepChange?.(id, 'failed'));
    throw new Error(
      '건축물대장 조회 서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인해 주세요.'
    );
  }

  if (!response.ok) {
    lookupIds.forEach((id) => onStepChange?.(id, 'failed'));
    throw new BuildingRegistryApiError(
      response.status,
      await getErrorDetail(response)
    );
  }

  const responseData = (await response.json()) as BuildingRegistryResponse;
  // 화면 확인용 `?mockFail=...` 동작을 유지해 항목별 실패 상태를 확인할 수 있다.
  const data: BuildingRegistryResponse = {
    ...responseData,
    titles: failLookups.includes('title') ? null : responseData.titles,
    floors: failLookups.includes('floor') ? null : responseData.floors,
    units: failLookups.includes('exclusiveArea') ? null : responseData.units,
    sewage: failLookups.includes('sewage') ? null : responseData.sewage,
  };
  const statusByLookup: Record<LookupId, boolean> = {
    title: data.titles !== null,
    floor: data.floors !== null,
    exclusiveArea: data.units !== null,
    sewage: data.sewage !== null,
  };
  lookupIds.forEach((id) =>
    onStepChange?.(id, statusByLookup[id] ? 'done' : 'failed')
  );

  return mapBuildingRegistryResponse(data, floorUnit);
}

async function getErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === 'object' &&
      'detail' in body &&
      typeof (body as { detail: unknown }).detail === 'string'
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // 오류 본문이 JSON이 아니면 아래의 안전한 기본 문구를 사용한다.
  }
  return '건축물대장 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.';
}

function mapBuildingRegistryResponse(
  data: BuildingRegistryResponse,
  floorUnit: string
): BuildingInfo {
  const title = data.titles?.[0] ?? null;
  const selectedFloor = parseFloorLabel(floorUnit);
  const selectedUnit = parseUnitName(floorUnit);
  const parkingSpaces = title?.parking_spaces ?? null;
  const floorRows = (data.floors ?? []).filter(
    (row) =>
      row.dong_name === (title?.dong_name ?? null) &&
      normalizeComparable(row.floor) === normalizeComparable(selectedFloor)
  );
  const unitRows = (data.units ?? []).filter(
    (row) =>
      row.dong_name === (title?.dong_name ?? null) &&
      normalizeComparable(row.floor) === normalizeComparable(selectedFloor)
  );

  const floorUses = [
    ...new Set(floorRows.map((row) => row.use).filter(isText)),
  ];
  const matchedUnit = selectedUnit
    ? unitRows.find(
        (row) =>
          normalizeComparable(row.unit_name) ===
          normalizeComparable(selectedUnit)
      )
    : unitRows.length === 1
      ? unitRows[0]
      : null;
  const sewageMethod =
    (data.sewage ?? []).find(
      (row): row is BuildingRegistrySewage & { method: SewageTreatment } =>
        row.method !== null && SEWAGE_OPTIONS.includes(row.method)
    )?.method ?? null;

  const floorCount = title?.ground_floors;
  const basementCount = title?.underground_floors;
  const floorCountLabel =
    floorCount === null || floorCount === undefined
      ? null
      : `지상 ${floorCount}층`;
  const basementCountLabel =
    basementCount === null || basementCount === undefined || basementCount === 0
      ? null
      : `지하 ${basementCount}층`;

  return {
    buildingName: title?.building_name ?? '건물명 확인 안 됨',
    floorLabel: selectedFloor,
    address: data.road_address ?? data.jibun_address ?? '',
    mainUse: registryField(title?.main_use ?? null),
    totalAreaM2: registryField(title?.total_area_m2 ?? null),
    floors: registryField(
      [floorCountLabel, basementCountLabel].filter(Boolean).join(' · ') || null
    ),
    floorUse: registryField(
      floorUses.length > 0 ? floorUses.join(' · ') : null
    ),
    exclusiveAreaM2: registryField(matchedUnit?.area_m2 ?? null),
    // 주차 대수가 1대 이상인 경우만 대장 기준 '가능'으로 채운다.
    parking: registryField<ParkingAvailability>(
      parkingSpaces !== null && parkingSpaces > 0 ? 'possible' : null
    ),
    facility: registryField(facilityFromMainUse(title?.main_use ?? null)),
    sewage: registryField(sewageMethod),
  };
}

function parseFloorLabel(floorUnit: string): string {
  const match = floorUnit.match(/(지하\s*)?\d+\s*층/);
  return match ? match[0].replace(/\s+/g, ' ') : '해당 층';
}

function parseUnitName(floorUnit: string): string | null {
  const match = floorUnit.match(/\d+\s*호/);
  return match ? match[0].replace(/\s+/g, '') : null;
}

function normalizeComparable(value: string | null | undefined): string {
  return (value ?? '').replace(/\s+/g, '');
}

function isText(value: string | null): value is string {
  return value !== null && value.trim().length > 0;
}

/**
 * 사용자가 고친 값을 반영한다. 건축물대장 값과 같아지면 다시 registry로,
 * 건축물대장에 없던 칸을 비우면 다시 missing으로 돌린다.
 */
export function editField<T>(
  field: BuildingField<T>,
  value: T | null
): BuildingField<T> {
  if (value === null) {
    return {
      ...field,
      value: null,
      source: field.registryValue === null ? 'missing' : 'user',
    };
  }
  return {
    ...field,
    value,
    source:
      field.registryValue !== null && value === field.registryValue
        ? 'registry'
        : 'user',
  };
}
