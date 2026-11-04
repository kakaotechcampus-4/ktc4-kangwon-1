import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  loadAnalysisResult,
  loadRequestId,
  loadVacancyInput,
  saveAnalysisResult,
  saveRequestId,
  saveVacancyInput,
} from '@/lib/api/resultStore';
import type { DecisionResult } from '@/lib/api/types';

beforeEach(() => {
  const items = new Map<string, string>();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('saveVacancyInput', () => {
  it('새 상가를 입력하면 이전 상가의 분석 결과와 요청 ID를 지운다', () => {
    saveAnalysisResult({ request_id: 'req-a' } as DecisionResult);
    saveRequestId('req-a');

    saveVacancyInput({ roadAddress: '서울 송파구 오금로 404', floorUnit: '' });

    expect(loadAnalysisResult()).toBeNull();
    expect(loadRequestId()).toBeNull();
    expect(loadVacancyInput()).toEqual({
      roadAddress: '서울 송파구 오금로 404',
      floorUnit: '',
    });
  });
});
