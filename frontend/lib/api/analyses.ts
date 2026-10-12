import type {
  AcceptedAnalysis,
  AnalysisEvents,
  AnswerSubmission,
  DecisionResult,
  StoredAnalysis,
} from '@/lib/api/types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

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
  } catch {
    // 본문이 JSON이 아니거나 detail이 없으면 상태 텍스트로 대체한다.
  }
  return response.statusText || '분석 요청에 실패했습니다.';
}

export async function createAnalysis(
  address: string,
  // mock 기본값은 false — docs/API_CONTRACT.md에 명시된 서버 기본값과
  // 맞춘다. 개발 중 백엔드 키 없이 화면만 확인하려면 호출부에서 임시로
  // { mock: true }를 넘긴다.
  options: { mock?: boolean; radiusM?: number } = {}
): Promise<{ result: DecisionResult; requestId: string }> {
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
    response = await fetch(`${API_BASE_URL}/api/v1/analyses?mock=${mock}`, {
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

  const result = (await response.json()) as DecisionResult;
  // 백엔드가 아직 X-Request-ID 응답 헤더를 내려주지 않으므로(현재
  // backend/app/api/v1/routes.py 기준), 헤더가 있으면 그걸 쓰고 없으면
  // 응답 본문의 request_id로 대체한다. 헤더가 추가되면 자동으로 그쪽을
  // 우선하게 된다.
  const requestId = response.headers.get('X-Request-ID') ?? result.request_id;

  return { result, requestId };
}

export async function getAnalysis(requestId: string): Promise<StoredAnalysis> {
  return requestJson<StoredAnalysis>(
    `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(requestId)}`
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
};

/**
 * 분석 요청 본문. 백엔드 AnalysisRequest는 정의되지 않은 필드를 422로
 * 거절하므로 여기서 정한 필드만 보낸다. 상가 정보 확인 화면의 주차·
 * 근린생활시설·오수정화시설은 백엔드 필드가 생기면 이 함수에 추가한다.
 */
export function buildAnalysisRequestBody({
  address,
  radiusM,
  allowQuestions = false,
}: AnalysisRequestInput): Record<string, unknown> {
  if (
    radiusM !== undefined &&
    (!Number.isSafeInteger(radiusM) || radiusM <= 0)
  ) {
    throw new Error('분석 반경은 미터 단위의 양의 정수로 입력해 주세요.');
  }
  return {
    address,
    ...(radiusM !== undefined ? { radius_m: radiusM } : {}),
    ...(allowQuestions ? { allow_questions: true } : {}),
  };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
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
export async function startAnalysis(
  input: AnalysisRequestInput
): Promise<AcceptedAnalysis> {
  return requestJson<AcceptedAnalysis>(
    `${API_BASE_URL}/api/v1/analyses?wait=false`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildAnalysisRequestBody(input)),
    }
  );
}

/** after 이후의 진행 이벤트. 다음 호출에는 응답의 next_after를 넘긴다. */
export async function getAnalysisEvents(
  requestId: string,
  after: number
): Promise<AnalysisEvents> {
  return requestJson<AnalysisEvents>(
    `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(requestId)}/events?after=${after}`
  );
}

/** 질문 답변을 제출하고 최종판단을 백그라운드로 재개한다(202). */
export async function submitAnswers(
  submission: AnswerSubmission
): Promise<AcceptedAnalysis> {
  return requestJson<AcceptedAnalysis>(
    `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(submission.request_id)}/answers?wait=false`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission),
    }
  );
}
