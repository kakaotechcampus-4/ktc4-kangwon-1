import type { DecisionResult, StoredAnalysis } from '@/lib/api/types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

// docs/API_CONTRACT.md: 실제 호출은 공공데이터 API를 100회 넘게 부르고
// 모델도 부른다. 수십 초가 걸릴 수 있다고 명시돼 있어 넉넉히 잡는다.
const CREATE_ANALYSIS_TIMEOUT_MS = 90_000;

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
  options: { mock?: boolean } = {}
): Promise<{ result: DecisionResult; requestId: string }> {
  const { mock = false } = options;

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
      body: JSON.stringify({ address }),
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
  const response = await fetch(
    `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(requestId)}`
  );

  if (response.status === 404) {
    throw new AnalysisApiError(404, '분석 요청을 찾을 수 없습니다.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new AnalysisApiError(response.status, detail);
  }

  return (await response.json()) as StoredAnalysis;
}
