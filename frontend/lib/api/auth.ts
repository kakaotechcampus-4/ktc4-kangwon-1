import { API_BASE_URL } from '@/lib/api/baseUrl';
import {
  ApiError,
  apiFetch,
  apiJson,
  jsonInit,
  readDetail,
} from '@/lib/api/http';

export type AuthUser = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  profile_image_url: string | null;
  email_verified: boolean;
  /** 이메일로 가입했는데 아직 메일 확인을 안 끝낸 상태. 분석 실행이 막힌다. */
  needs_verification: boolean;
  created_at: string | null;
};

export type MyAnalysis = {
  request_id: string;
  input_address: string;
  status: string;
  created_at: string;
  completed_at: string | null;
};

export type MyAnalyses = {
  items: MyAnalysis[];
  total: number;
  limit: number;
  offset: number;
};

/** 로그인돼 있지 않으면 null. 401은 오류가 아니라 "비로그인"이라는 답이다. */
export async function getMe(): Promise<AuthUser | null> {
  const response = await apiFetch('/api/v1/auth/me');
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as AuthUser;
}

export async function signup(input: {
  email: string;
  password: string;
  displayName?: string;
}): Promise<{ verification_sent: boolean }> {
  return apiJson(
    '/api/v1/auth/signup',
    jsonInit('POST', {
      email: input.email,
      password: input.password,
      ...(input.displayName ? { display_name: input.displayName } : {}),
    })
  );
}

export async function login(email: string, password: string): Promise<void> {
  await apiJson('/api/v1/auth/login', jsonInit('POST', { email, password }));
}

export async function logout(): Promise<void> {
  await apiJson('/api/v1/auth/logout', { method: 'POST' });
}

export async function verifyEmail(token: string): Promise<void> {
  await apiJson('/api/v1/auth/verify-email', jsonInit('POST', { token }));
}

export async function resendVerification(): Promise<{
  verification_sent: boolean;
}> {
  return apiJson('/api/v1/auth/verification/resend', { method: 'POST' });
}

export async function forgotPassword(email: string): Promise<void> {
  await apiJson('/api/v1/auth/password/forgot', jsonInit('POST', { email }));
}

export async function resetPassword(
  token: string,
  newPassword: string
): Promise<void> {
  await apiJson(
    '/api/v1/auth/password/reset',
    jsonInit('POST', { token, new_password: newPassword })
  );
}

export async function getMyAnalyses(
  options: { limit?: number; offset?: number } = {}
): Promise<MyAnalyses> {
  const { limit = 20, offset = 0 } = options;
  return apiJson(`/api/v1/me/analyses?limit=${limit}&offset=${offset}`);
}

/**
 * 카카오 로그인 주소. fetch가 아니라 주소창 이동으로 열어야 한다.
 * 쿠키는 백엔드가 직접 심으므로 브라우저가 그쪽으로 실제로 이동해야 한다.
 */
export function kakaoLoginUrl(next: string): string {
  return `${API_BASE_URL}/api/v1/auth/kakao/login?next=${encodeURIComponent(safeNext(next))}`;
}

const MAX_NEXT_LENGTH = 200;

/** 바깥 주소로 튕기지 않게 우리 경로만 허용한다. 백엔드도 같은 검사를 한다. */
export function safeNext(path: string | null | undefined): string {
  if (!path) {
    return '/';
  }
  const candidate = path.trim();
  if (candidate.length > MAX_NEXT_LENGTH || !candidate.startsWith('/')) {
    return '/';
  }
  // `//evil.com` 과 `/\evil.com` 은 브라우저가 스킴 생략 절대주소로 읽는다.
  if (candidate.startsWith('//') || candidate.startsWith('/\\')) {
    return '/';
  }
  return candidate;
}

/** 로그인 화면이 ?error= 로 받는 카카오 실패 사유. */
export const KAKAO_ERRORS: Record<string, string> = {
  cancelled: '카카오 로그인을 취소했습니다.',
  expired: '로그인 요청이 만료되었습니다. 다시 시도해 주세요.',
  failed: '카카오 로그인에 실패했습니다. 다시 시도해 주세요.',
  unavailable:
    '카카오 로그인을 지금 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.',
};
