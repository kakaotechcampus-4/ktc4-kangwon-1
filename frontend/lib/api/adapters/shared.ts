/**
 * 어댑터(commercialArea.ts, businessLifecycle.ts, floatingPopulation.ts)가
 * 공통으로 쓰는 null 안전 파싱 헬퍼. 백엔드가 계약과 다른 값을 내려줘도
 * 화면이 깨지지 않도록, "기대한 타입이 아니면 안전한 기본값"으로 통일한다.
 */

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function asNullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

export function asStringArray(value: unknown): string[] {
  return asArray(value).filter((v): v is string => typeof v === 'string');
}
