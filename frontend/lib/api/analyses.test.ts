import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildAnalysisRequestBody, createAnalysis } from './analyses';

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

describe('확인 화면 층·전용면적 전달', () => {
  it('층과 전용면적을 함께 보낸다', () => {
    expect(
      buildAnalysisRequestBody({
        address: '테스트 주소',
        allowQuestions: true,
        floor: '4층',
        exclusiveAreaM2: 93.6,
      })
    ).toEqual({
      address: '테스트 주소',
      allow_questions: true,
      floor: '4층',
      exclusive_area_m2: 93.6,
    });
  });

  it.each([0, 0.001, -1, NaN, Infinity, 100001])(
    '잘못된 전용면적 %s는 빼고 보낸다',
    (exclusiveAreaM2) => {
      expect(
        buildAnalysisRequestBody({ address: '테스트 주소', exclusiveAreaM2 })
      ).toEqual({ address: '테스트 주소' });
    }
  );

  it.each(['', '해당 층', '4층 401호', '지하1층'])(
    '규칙 밖의 층 %s는 빼고 보낸다',
    (floor) => {
      expect(
        buildAnalysisRequestBody({ address: '테스트 주소', floor })
      ).toEqual({ address: '테스트 주소' });
    }
  );
});
