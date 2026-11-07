import type { FactView } from '@/lib/api/types';

/**
 * 이 상가가 교육환경보호구역 안인지.
 *
 * 서버가 V-World 고시 구역 다각형에 좌표가 실제로 들어가는지까지 확인한 뒤
 * `regulation / zone_contains` fact로 남긴다. 확인하지 못한 경우(status가
 * observed가 아님)는 모름으로 둔다 — 모르는 것을 "해당 없음"으로 바꾸지 않는다.
 */
export type EducationZoneStatus = 'inside' | 'outside' | 'unknown';

export const EDUCATION_ZONE_LABELS: Record<EducationZoneStatus, string> = {
  inside: '해당',
  outside: '해당 없음',
  unknown: '확인 필요',
};

export function educationZoneStatus(facts: FactView[]): EducationZoneStatus {
  const zone = facts.find(
    (fact) => fact.source === 'regulation' && fact.metric === 'zone_contains'
  );
  if (!zone || zone.status !== 'observed') {
    return 'unknown';
  }
  return zone.value === true ? 'inside' : 'outside';
}
