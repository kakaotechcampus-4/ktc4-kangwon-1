import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  KAKAO_ERRORS,
  kakaoLoginUrl,
  loginPath,
  safeNext,
  signup,
} from '@/lib/api/auth';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('signup', () => {
  it('서버가 받는 세 칸만 agree_terms 이름으로 보낸다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ user_id: 'u1', verification_sent: true }), {
        status: 201,
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    await signup({
      email: 'a@b.com',
      password: '1234567890',
      agreeTerms: true,
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith('/api/v1/auth/signup')).toBe(true);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toStrictEqual({
      email: 'a@b.com',
      password: '1234567890',
      agree_terms: true,
    });
  });
});

describe('loginPath', () => {
  it('로그인 뒤 돌아올 주소에 쿼리까지 담는다', () => {
    const path = loginPath('/analysis-progress', '?id=abc123');
    const next = new URLSearchParams(path.split('?')[1]).get('next');
    expect(path.startsWith('/login?next=')).toBe(true);
    expect(safeNext(next)).toBe('/analysis-progress?id=abc123');
  });

  it('쿼리가 없으면 경로만 담는다', () => {
    expect(loginPath('/report', '')).toBe('/login?next=%2Freport');
  });
});

describe('safeNext', () => {
  it('우리 경로는 그대로 돌려준다', () => {
    expect(safeNext('/vacancy-input')).toBe('/vacancy-input');
    expect(safeNext('/report?tab=1')).toBe('/report?tab=1');
  });

  it('바깥 주소는 전부 기본 경로로 바꾼다', () => {
    // `//`와 `/\`는 브라우저가 스킴 생략 절대주소로 읽어 외부로 튕긴다.
    for (const evil of [
      'https://evil.example/steal',
      '//evil.example',
      '/\\evil.example',
      'javascript:alert(1)',
      'vacancy-input',
      '/\t/evil.example',
      '/\n/evil.example',
    ]) {
      expect(safeNext(evil)).toBe('/');
    }
  });

  it('빈 값과 지나치게 긴 경로를 막는다', () => {
    expect(safeNext(null)).toBe('/');
    expect(safeNext(undefined)).toBe('/');
    expect(safeNext('')).toBe('/');
    expect(safeNext(`/${'x'.repeat(300)}`)).toBe('/');
  });
});

describe('kakaoLoginUrl', () => {
  it('next를 검사한 뒤 인코딩해 붙인다', () => {
    expect(kakaoLoginUrl('/vacancy-input')).toContain('next=%2Fvacancy-input');
  });

  it('바깥 주소를 next로 넘겨도 실어 보내지 않는다', () => {
    const url = kakaoLoginUrl('https://evil.example');
    expect(url).toContain('next=%2F');
    expect(url).not.toContain('evil.example');
  });
});

describe('KAKAO_ERRORS', () => {
  it('백엔드가 보내는 네 가지 사유를 모두 설명한다', () => {
    // app/api/v1/auth.py 의 _CALLBACK_ERRORS 와 짝이 맞아야 한다.
    expect(Object.keys(KAKAO_ERRORS).sort()).toEqual([
      'cancelled',
      'expired',
      'failed',
      'unavailable',
    ]);
  });
});
