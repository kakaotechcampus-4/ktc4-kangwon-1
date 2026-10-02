/**
 * 상가 정보 확인(/building-confirm) 화면이 쓰는 건축물대장 조회.
 *
 * 백엔드에 국토교통부 건축물대장 HUB 연동이 아직 없어 지금은 mock 응답을
 * setTimeout으로 항목별 순차 완료시키며 돌려준다. 실제 API가 생기면
 * fetchBuildingInfo 안쪽만 바꾸면 되도록, 화면은 아래 타입과 onStepChange
 * 콜백에만 의존한다.
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
  // 화면 확인용: 여기 넣은 항목은 일부러 실패시켜 missing 흐름을 볼 수 있다.
  failLookups?: LookupId[];
};

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

// mock — 9/17 건축물대장 HUB 실호출 결과(성희프라자 4층)를 옮겨 둔 값
const MOCK_REGISTRY = {
  buildingName: '성희프라자',
  floorLabel: '4층',
  address: '위례광장로 199',
  sourceNote: '9/17 실호출 결과를 예시로 넣었어요',
  title: {
    mainUse: '제2종근린생활시설',
    totalAreaM2: 12301.78,
    floors: '지상 7층',
  },
  floor: { floorUse: '일반음식점' },
  exclusiveArea: { exclusiveAreaM2: 275.49 },
  sewage: { sewage: '하수종말처리장 연결' as SewageTreatment },
};
const MOCK_STEP_MS = 700;

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('조회가 취소됐습니다.', 'AbortError'));
    });
  });
}

/**
 * 건축물대장 4개 항목을 차례로 조회한다. 한 항목이 실패해도 멈추지 않고,
 * 그 항목에서 오는 필드를 missing으로 채워 돌려준다.
 */
export async function fetchBuildingInfo(
  address: string,
  { onStepChange, signal, failLookups = [] }: FetchOptions = {}
): Promise<BuildingInfo> {
  void address; // mock 단계 — 실제 API에서는 이 주소로 조회한다.
  const results: Partial<Record<LookupId, boolean>> = {};

  for (const id of LOOKUP_ORDER) {
    onStepChange?.(id, 'loading');
    await wait(MOCK_STEP_MS, signal);
    const ok = !failLookups.includes(id);
    results[id] = ok;
    onStepChange?.(id, ok ? 'done' : 'failed');
  }

  const title = results.title ? MOCK_REGISTRY.title : null;
  const mainUse = title?.mainUse ?? null;

  return {
    buildingName: MOCK_REGISTRY.buildingName,
    floorLabel: MOCK_REGISTRY.floorLabel,
    address: MOCK_REGISTRY.address,
    sourceNote: MOCK_REGISTRY.sourceNote,
    mainUse: registryField(mainUse),
    totalAreaM2: registryField(title?.totalAreaM2 ?? null),
    floors: registryField(title?.floors ?? null),
    floorUse: registryField(
      results.floor ? MOCK_REGISTRY.floor.floorUse : null
    ),
    exclusiveAreaM2: registryField(
      results.exclusiveArea ? MOCK_REGISTRY.exclusiveArea.exclusiveAreaM2 : null
    ),
    // 주차는 건축물대장에 없는 항목이라 항상 missing으로 시작한다.
    parking: registryField<ParkingAvailability>(null),
    facility: registryField(facilityFromMainUse(mainUse)),
    sewage: registryField(results.sewage ? MOCK_REGISTRY.sewage.sewage : null),
  };
}
