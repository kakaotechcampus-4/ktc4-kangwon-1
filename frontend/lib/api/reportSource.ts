import type { DecisionResult, StoredAnalysis } from '@/lib/api/types';
import type { VacancyInput } from '@/lib/api/resultStore';
import { formatDay } from '@/lib/api/analysisStatus';

export type ReportSource =
  | { kind: 'saved'; result: DecisionResult }
  | { kind: 'fetch'; requestId: string }
  | { kind: 'preview' }
  | { kind: 'example' }
  | { kind: 'empty' };

export function reportSource({
  urlId,
  savedRequestId,
  saved,
  mockMode,
  example,
}: {
  urlId: string | null;
  savedRequestId: string | null;
  saved: DecisionResult | null;
  mockMode: boolean;
  example: boolean;
}): ReportSource {
  if (example) {
    return { kind: 'example' };
  }
  if (urlId) {
    return { kind: 'fetch', requestId: urlId };
  }
  if (saved && (!savedRequestId || saved.request_id === savedRequestId)) {
    return { kind: 'saved', result: saved };
  }
  if (savedRequestId) {
    return { kind: 'fetch', requestId: savedRequestId };
  }
  return mockMode ? { kind: 'preview' } : { kind: 'empty' };
}

export type Coordinates = { latitude: number; longitude: number };

export type StoredReport =
  | {
      kind: 'ready';
      result: DecisionResult;
      vacancyInput: VacancyInput | null;
      coordinates: Coordinates | null;
      analyzedDate: string;
    }
  | { kind: 'pending'; requestId: string }
  | { kind: 'failed'; message: string };

const text = (value: unknown) =>
  typeof value === 'string' && value.trim() ? value.trim() : null;

// 0은 좌표로 치지 않는다. 서울 상가가 적도 한가운데에 있을 수 없고,
// 좌표를 못 구한 옛 기록이 0으로 저장돼 있어 그대로 믿으면 엉뚱한 바다를 그린다.
const coordinate = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value !== 0
    ? value
    : null;

// 분석이 실제로 쓴 좌표. 지도는 주소를 다시 찾지 않고 이 값을 중심으로 삼는다.
// 하나라도 빠지면 좌표로 치지 않는다 — 위도만 맞는 지도는 틀린 지도다.
function coordinatesFromStored(detail: StoredAnalysis): Coordinates | null {
  const latitude = coordinate(detail.site?.latitude);
  const longitude = coordinate(detail.site?.longitude);
  return latitude === null || longitude === null
    ? null
    : { latitude, longitude };
}

export function vacancyFromStored(detail: StoredAnalysis): VacancyInput | null {
  const site = detail.site;
  const address =
    text(site?.road_address) ??
    text(site?.jibun_address) ??
    text(site?.input_address);
  if (address) {
    return {
      roadAddress: address,
      floorUnit: text(site?.detail_address) ?? '',
    };
  }
  const input = text(detail.input_address);
  return input ? { roadAddress: input, floorUnit: '' } : null;
}

export function storedReport(detail: StoredAnalysis): StoredReport {
  if (detail.status === 'completed' && detail.result) {
    return {
      kind: 'ready',
      result: detail.result,
      vacancyInput: vacancyFromStored(detail),
      coordinates: coordinatesFromStored(detail),
      analyzedDate: formatDay(detail.completed_at ?? null),
    };
  }
  if (detail.status === 'failed' || detail.status === 'completed') {
    return {
      kind: 'failed',
      message: detail.error?.message ?? '분석을 끝까지 마치지 못했어요.',
    };
  }
  return { kind: 'pending', requestId: detail.request_id };
}

export function isExampleReport(search: string): boolean {
  const params = new URLSearchParams(search);
  return params.has('example') || params.has('demo');
}
