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

export type StoredReport =
  | {
      kind: 'ready';
      result: DecisionResult;
      vacancyInput: VacancyInput | null;
      analyzedDate: string;
    }
  | { kind: 'pending'; requestId: string }
  | { kind: 'failed'; message: string };

const text = (value: unknown) =>
  typeof value === 'string' && value.trim() ? value.trim() : null;

function vacancyFromStored(detail: StoredAnalysis): VacancyInput | null {
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
