import type {
  AcceptedAnalysis,
  AnalysisEvents,
  AnswerSubmission,
  DecisionResult,
  FacilityKey,
  FacilityState,
  RequestFacts,
  StoredAnalysis,
  WaitingForInput,
} from '@/lib/api/types';
import { apiFetch } from '@/lib/api/http';

// docs/API_CONTRACT.md: 실제 호출은 공공데이터 API를 100회 넘게 부르고
// 모델도 부른다. 수십 초가 걸릴 수 있다고 명시돼 있어 넉넉히 잡는다.
const CREATE_ANALYSIS_TIMEOUT_MS = 600_000;

export class AnalysisApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'AnalysisApiError';
    this.status = status;
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
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
    // FastAPI 검증 오류(422)는 detail이 [{loc, msg, type}] 목록으로 온다.
    // 화면에는 한국어 안내만 띄우고, 어떤 값이 왜 틀렸는지는 콘솔에 남긴다.
    if (body && typeof body === 'object' && 'detail' in body) {
      console.warn(
        `[api] ${response.status} ${response.url}`,
        (body as { detail: unknown }).detail
      );
      if (response.status === 422) {
        return '요청 값이 올바르지 않아 처리하지 못했어요. 입력한 정보를 확인해 주세요.';
      }
    }
  } catch {
    // 본문이 JSON이 아니거나 detail이 없으면 상태 텍스트로 대체한다.
  }
  return response.status === 422
    ? '요청 값이 올바르지 않아 처리하지 못했어요. 입력한 정보를 확인해 주세요.'
    : '분석 요청에 실패했어요. 잠시 후 다시 시도해 주세요.';
}

export async function createAnalysis(
  address: string,
  // mock 기본값은 false — docs/API_CONTRACT.md에 명시된 서버 기본값과
  // 맞춘다. 개발 중 백엔드 키 없이 화면만 확인하려면 호출부에서 임시로
  // { mock: true }를 넘긴다.
  options: { mock?: boolean; radiusM?: number } = {}
): Promise<{ result: DecisionResult | WaitingForInput; requestId: string }> {
  const { mock = false, radiusM } = options;
  if (
    radiusM !== undefined &&
    (!Number.isSafeInteger(radiusM) || radiusM <= 0)
  ) {
    throw new Error('분석 반경은 미터 단위의 양의 정수로 입력해 주세요.');
  }

  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    CREATE_ANALYSIS_TIMEOUT_MS
  );

  let response: Response;
  try {
    response = await apiFetch(`/api/v1/analyses?mock=${mock}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // radius_m은 백엔드 요청 필드 제안이며, 서버의 수신·적용 연결이 필요하다.
      body: JSON.stringify({
        address,
        ...(radiusM !== undefined ? { radius_m: radiusM } : {}),
      }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(
        '분석에 시간이 오래 걸리고 있습니다. 잠시 후 다시 시도해주세요.'
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new AnalysisApiError(response.status, detail);
  }

  // allow_questions를 보내지 않으므로 보통 최종 결과지만, 계약상 질문 대기도 올 수 있다.
  const result = (await response.json()) as DecisionResult | WaitingForInput;
  // X-Request-ID 헤더를 우선하고, 없으면 응답 본문의 request_id로 대체한다.
  const requestId = response.headers.get('X-Request-ID') ?? result.request_id;

  return { result, requestId };
}

export async function getAnalysis(requestId: string): Promise<StoredAnalysis> {
  return requestJson<StoredAnalysis>(
    `/api/v1/analyses/${encodeURIComponent(requestId)}`
  );
}

// ---------------------------------------------------------------------------
// 진행 화면용 비동기 흐름 (docs/API_CONTRACT.md "비동기 실행과 진행 이벤트")
//   POST /analyses?wait=false → 202 → GET /events 폴링 → GET /analyses/{id}
//   질문 대기면 POST /answers?wait=false → 다시 events 폴링
// ---------------------------------------------------------------------------

export type AnalysisRequestInput = {
  address: string;
  radiusM?: number;
  allowQuestions?: boolean;
  floor?: string;
  exclusiveAreaM2?: number;
  facilities?: Partial<Record<FacilityKey, FacilityState>>;
};

const FLOOR_PATTERN = /^(지하 )?[1-9]\d{0,2}층$/;

function knownFacilities(
  facilities: AnalysisRequestInput['facilities']
): Partial<Record<FacilityKey, FacilityState>> | null {
  const known = Object.fromEntries(
    Object.entries(facilities ?? {}).filter(([, state]) => state !== 'unknown')
  );
  return Object.keys(known).length > 0 ? known : null;
}

function validArea(value: number | undefined): value is number {
  return (
    value !== undefined &&
    Number.isFinite(value) &&
    value >= 0.01 &&
    value <= 100000
  );
}

/**
 * 분석 요청 본문. 백엔드 AnalysisRequest는 정의되지 않은 필드를 422로
 * 거절하므로 여기서 정한 필드만 보낸다. 상가 정보 확인 화면의 주차·
 * 근린생활시설·오수정화시설은 백엔드 필드가 생기면 이 함수에 추가한다.
 */
export function buildAnalysisRequestBody({
  address,
  radiusM,
  allowQuestions = false,
  floor,
  exclusiveAreaM2,
  facilities,
}: AnalysisRequestInput): Record<string, unknown> {
  if (
    radiusM !== undefined &&
    (!Number.isSafeInteger(radiusM) || radiusM <= 0)
  ) {
    throw new Error('분석 반경은 미터 단위의 양의 정수로 입력해 주세요.');
  }
  const known = knownFacilities(facilities);
  return {
    address,
    ...(radiusM !== undefined ? { radius_m: radiusM } : {}),
    ...(allowQuestions ? { allow_questions: true } : {}),
    ...(floor !== undefined && FLOOR_PATTERN.test(floor) ? { floor } : {}),
    ...(validArea(exclusiveAreaM2)
      ? { exclusive_area_m2: exclusiveAreaM2 }
      : {}),
    ...(known ? { facilities: known } : {}),
  };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  return readJson<T>(await apiFetch(url, init));
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new AnalysisApiError(
      response.status,
      response.status === 404
        ? '분석 요청을 찾을 수 없습니다.'
        : await parseErrorDetail(response)
    );
  }
  return (await response.json()) as T;
}

/** 분석을 백그라운드로 시작하고 request_id를 바로 받는다(202). */
async function rejectsFacilities(response: Response): Promise<boolean> {
  if (response.status !== 422) {
    return false;
  }
  try {
    const body: unknown = await response.clone().json();
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? (body as { detail: unknown }).detail
        : null;
    return (
      Array.isArray(detail) &&
      detail.some((item: unknown) => {
        const loc =
          item && typeof item === 'object' && 'loc' in item
            ? (item as { loc: unknown }).loc
            : null;
        return (
          Array.isArray(loc) && loc[0] === 'body' && loc[1] === 'facilities'
        );
      })
    );
  } catch {
    return false;
  }
}

export async function startAnalysis(
  input: AnalysisRequestInput
): Promise<AcceptedAnalysis & { facilitiesDropped?: boolean }> {
  const url = `/api/v1/analyses?wait=false`;
  const body = buildAnalysisRequestBody(input);
  const send = (payload: object) =>
    requestJson<AcceptedAnalysis>(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  if (!('facilities' in body)) {
    return send(body);
  }
  const response = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (await rejectsFacilities(response)) {
    const withoutFacilities: Record<string, unknown> = { ...body };
    delete withoutFacilities.facilities;
    return { ...(await send(withoutFacilities)), facilitiesDropped: true };
  }
  return readJson<AcceptedAnalysis>(response);
}

/** after 이후의 진행 이벤트. 다음 호출에는 응답의 next_after를 넘긴다. */
export async function getAnalysisEvents(
  requestId: string,
  after: number
): Promise<AnalysisEvents> {
  return requestJson<AnalysisEvents>(
    `/api/v1/analyses/${encodeURIComponent(requestId)}/events?after=${after}`
  );
}

/** 질문 답변을 제출하고 최종판단을 백그라운드로 재개한다(202). */
export async function submitAnswers(
  submission: AnswerSubmission
): Promise<AcceptedAnalysis> {
  const { request_id, question_session_id, answers } = submission;
  return requestJson<AcceptedAnalysis>(
    `/api/v1/analyses/${encodeURIComponent(request_id)}/answers?wait=false`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 백엔드 Answers는 정의되지 않은 필드를 422로 거절한다(request_id는 URL에만).
      body: JSON.stringify({ question_session_id, answers }),
    }
  );
}

/** 리포트 차트용 전체 fact. 결과의 facts는 보고서가 인용한 것만 담는다. */
export async function getAnalysisFacts(
  requestId: string
): Promise<RequestFacts> {
  return requestJson<RequestFacts>(
    `/api/v1/analyses/${encodeURIComponent(requestId)}/facts`
  );
}
