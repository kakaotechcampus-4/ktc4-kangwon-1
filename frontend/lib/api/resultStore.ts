import type { DecisionResult } from '@/lib/api/types';

const RESULT_STORAGE_KEY = 'chum:lastAnalysis';
const REQUEST_ID_STORAGE_KEY = 'chum:lastRequestId';

export function saveAnalysisResult(result: DecisionResult): void {
  sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(result));
}

export function loadAnalysisResult(): DecisionResult | null {
  const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as DecisionResult;
  } catch {
    return null;
  }
}

export function clearAnalysisResult(): void {
  sessionStorage.removeItem(RESULT_STORAGE_KEY);
}

export function saveRequestId(requestId: string): void {
  sessionStorage.setItem(REQUEST_ID_STORAGE_KEY, requestId);
}

export function loadRequestId(): string | null {
  return sessionStorage.getItem(REQUEST_ID_STORAGE_KEY);
}

export function clearRequestId(): void {
  sessionStorage.removeItem(REQUEST_ID_STORAGE_KEY);
}
