import { API_BASE_URL } from '@/lib/api/baseUrl';

/**
 * 백엔드 호출을 한 곳으로 모은다. 세션이 쿠키에 있어서 credentials를 빠뜨리면
 * 그 호출만 조용히 비로그인으로 처리된다. 호출부마다 붙이면 언젠가 빠뜨린다.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** 로그인이 풀렸을 때 화면이 반응하도록 AuthProvider가 등록한다. */
type UnauthorizedHandler = (status: 401 | 403) => void;
let handleUnauthorized: UnauthorizedHandler | null = null;

export function onUnauthorized(handler: UnauthorizedHandler | null): void {
  handleUnauthorized = handler;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    // 쿠키 인증이라 교차 출처 호출에는 이 옵션이 있어야 세션이 붙는다.
    credentials: 'include',
  });

  if (response.status === 401 || response.status === 403) {
    handleUnauthorized?.(response.status);
  }
  return response;
}

/** 본문이 JSON인 요청. Content-Type과 Origin 검사 대상 메서드를 함께 맞춘다. */
export function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string') {
        return detail;
      }
    }
  } catch {
    // 본문이 JSON이 아니면 상태 텍스트로 대신한다.
  }
  return response.statusText || '요청을 처리하지 못했습니다.';
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}
