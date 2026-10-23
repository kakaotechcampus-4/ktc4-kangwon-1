import {
  normalizeFloor,
  type LookupId,
  type NeighborhoodFacility,
  type ParkingAvailability,
} from '@/lib/api/building';

// 상가 정보 확인 화면의 표시 문구 — 컴포넌트 여러 곳에서 같이 쓴다.

export const LOOKUP_LABELS: Record<
  LookupId,
  { title: string; description: (floorLabel: string) => string }
> = {
  title: { title: '표제부', description: () => '건물 주용도 · 연면적 · 층수' },
  floor: {
    title: '층별개요',
    description: (floorLabel) => `${floorLabel} 용도 · 면적`,
  },
  exclusiveArea: { title: '전유공용면적', description: () => '호실 전용면적' },
  sewage: { title: '오수정화시설', description: () => '오수 처리 방식' },
};

export const PARKING_LABELS: Record<ParkingAvailability, string> = {
  possible: '가능',
  impossible: '불가',
  unknown: '모름',
};

export const FACILITY_LABELS: Record<NeighborhoodFacility, string> = {
  type1: '제1종 근린생활시설',
  type2: '제2종 근린생활시설',
  none: '해당없음',
};

// 세그먼트 버튼은 칸이 좁아 짧은 이름을 쓴다.
export const FACILITY_SHORT_LABELS: Record<NeighborhoodFacility, string> = {
  type1: '제1종',
  type2: '제2종',
  none: '해당없음',
};

export function formatArea(value: number): string {
  return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}㎡`;
}

// 백엔드 공간 비교와 같은 표기를 지원하며, 지하 접두어를 버리고 지상층으로 읽지 않는다.
export function floorFromUnit(floorUnit: string): string {
  return normalizeFloor(floorUnit) ?? '해당 층';
}
