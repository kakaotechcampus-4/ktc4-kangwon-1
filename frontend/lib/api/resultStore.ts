import type { BuildingInfo } from '@/lib/api/building';
import type { DecisionResult } from '@/lib/api/types';

const RESULT_STORAGE_KEY = 'chaeum:lastAnalysis';
const REQUEST_ID_STORAGE_KEY = 'chaeum:lastRequestId';

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

// 공실 입력값 — 공실 입력 화면에서 저장하고, 상가 정보 확인 화면이 읽어
// 분석 요청을 보낸다. radius는 입력칸 그대로(빈 문자열 가능)라 요청 시 변환한다.
const VACANCY_INPUT_STORAGE_KEY = 'chaeum:vacancyInput';

export type VacancyInput = {
  roadAddress: string;
  floorUnit: string;
  radius: string;
};

export function saveVacancyInput(input: VacancyInput): void {
  sessionStorage.setItem(VACANCY_INPUT_STORAGE_KEY, JSON.stringify(input));
}

export function loadVacancyInput(): VacancyInput | null {
  const raw = sessionStorage.getItem(VACANCY_INPUT_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as VacancyInput;
  } catch {
    return null;
  }
}

// 상가 정보 확인 화면에서 사용자가 확인(또는 수정)한 건축물 정보.
// 분석 요청 본문에는 넣지 않고 화면 표시용으로만 남긴다.
const CONFIRMED_BUILDING_STORAGE_KEY = 'chaeum:confirmedBuilding';

export function saveConfirmedBuilding(building: BuildingInfo): void {
  sessionStorage.setItem(
    CONFIRMED_BUILDING_STORAGE_KEY,
    JSON.stringify(building)
  );
}

export function loadConfirmedBuilding(): BuildingInfo | null {
  const raw = sessionStorage.getItem(CONFIRMED_BUILDING_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as BuildingInfo;
  } catch {
    return null;
  }
}
