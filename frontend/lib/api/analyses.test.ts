import { afterEach, describe, expect, it, vi } from 'vitest';
import { createAnalysis } from './analyses';

afterEach(() => vi.unstubAllGlobals());

function mockFetch() {
  const fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ request_id: 'test-request' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

describe('분석 요청의 반경 전달', () => {
  it('선택한 미터 반경을 radius_m으로 전달한다', async () => {
    const fetch = mockFetch();
    await createAnalysis('테스트 주소', { radiusM: 750, mock: true });
    expect(fetch.mock.calls[0][0]).toContain('/api/v1/analyses?mock=true');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      address: '테스트 주소',
      radius_m: 750,
    });
  });

  it('반경이 없으면 주소만 전달한다', async () => {
    const fetch = mockFetch();
    await createAnalysis('테스트 주소');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      address: '테스트 주소',
    });
  });

  it.each([0, -100, 1.5, NaN, Infinity])(
    '잘못된 반경 %s는 요청 전에 거부한다',
    async (radiusM) => {
      const fetch = mockFetch();
      await expect(createAnalysis('테스트 주소', { radiusM })).rejects.toThrow(
        '분석 반경은 미터 단위의 양의 정수'
      );
      expect(fetch).not.toHaveBeenCalled();
    }
  );
});
