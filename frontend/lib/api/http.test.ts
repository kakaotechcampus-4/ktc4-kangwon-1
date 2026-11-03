import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  NETWORK_ERROR_MESSAGE,
  SERVER_BUSY_MESSAGE,
  apiFetch,
  readDetail,
} from '@/lib/api/http';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiFetch', () => {
  it('인터넷이 끊기면 영어 대신 한국어 ApiError를 던진다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    );
    const caught = await apiFetch('/api/v1/auth/me').catch((e: unknown) => e);
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(0);
    expect((caught as ApiError).message).toBe(NETWORK_ERROR_MESSAGE);
  });

  it('취소(AbortError)는 그대로 넘긴다', async () => {
    const abort = new DOMException('x', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
    await expect(apiFetch('/api/v1/auth/me')).rejects.toBe(abort);
  });

  it('다른 실행 환경의 취소 오류도 이름으로 알아보고 그대로 넘긴다', async () => {
    const abort = Object.assign(new Error('x'), { name: 'AbortError' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort));
    await expect(apiFetch('/api/v1/auth/me')).rejects.toBe(abort);
  });
});

describe('readDetail', () => {
  it('게이트웨이가 HTML로 답하면 잠시 뒤 다시 하라는 한국어 안내를 쓴다', async () => {
    const response = new Response('<html>', {
      status: 502,
      statusText: 'Bad Gateway',
    });
    expect(await readDetail(response)).toBe(SERVER_BUSY_MESSAGE);
  });

  it('영어 상태 문구는 보여 주지 않는다', async () => {
    const response = new Response(
      JSON.stringify({ detail: [{ loc: ['body'], msg: 'x' }] }),
      { status: 422, statusText: 'Unprocessable Entity' }
    );
    expect(await readDetail(response)).toBe('요청을 처리하지 못했습니다.');
  });
});
