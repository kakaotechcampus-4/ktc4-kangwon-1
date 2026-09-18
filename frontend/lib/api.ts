/**
 * 백엔드(FastAPI) 호출 전용 모듈입니다.
 * 계약: docs/API_CONTRACT.md, backend/app/schemas.py.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

// 실제 호출은 공공데이터 API 100회 이상 + LLM 호출이 나가서 수십 초가 걸릴 수 있다
// (docs/API_CONTRACT.md "응답이 느립니다"). 넉넉히 잡는다.
const ANALYSIS_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
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
    // 본문이 JSON이 아니면 상태 텍스트로 대체한다.
  }
  return response.statusText || '알 수 없는 오류가 발생했습니다.';
}

/**
 * 주소 하나로 분석을 실행합니다. 응답이 올 때까지(최종 리포트) 기다립니다.
 */
export async function postAnalysis(
  address: string,
  options?: { mock?: boolean }
): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);

  const query = options?.mock ? '?mock=true' : '';
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/analyses${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new ApiError(response.status, await parseErrorDetail(response));
    }
    return await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, '분석이 너무 오래 걸려 요청을 중단했습니다.');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * 저장된 분석 요청/결과를 request_id로 조회합니다.
 */
export async function getAnalysis(requestId: string): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyses/${requestId}`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return await response.json();
}
