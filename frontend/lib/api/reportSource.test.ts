import { describe, expect, it } from 'vitest';
import {
  isExampleReport,
  reportSource,
  storedReport,
} from '@/lib/api/reportSource';
import type { DecisionResult, StoredAnalysis } from '@/lib/api/types';

const resultFor = (requestId: string) =>
  ({ request_id: requestId }) as DecisionResult;

function stored(overrides: Partial<StoredAnalysis>): StoredAnalysis {
  return {
    request_id: 'req-b',
    status: 'completed',
    site: {
      input_address: '서울 송파구 오금로 404 2층 201호',
      road_address: '서울특별시 송파구 오금로 404',
      detail_address: '2층 201호',
    },
    result: resultFor('req-b'),
    error: null,
    questions: null,
    rendered: null,
    input_address: '서울 송파구 오금로 404 2층 201호',
    completed_at: '2026-10-27T12:00:00+00:00',
    ...overrides,
  };
}

const base = {
  urlId: null,
  savedRequestId: null,
  saved: null,
  mockMode: false,
  example: false,
};

describe('reportSource', () => {
  it('주소의 ID가 탭에 남은 결과와 다르면 그 ID를 서버에서 받는다', () => {
    expect(
      reportSource({
        ...base,
        urlId: 'req-b',
        savedRequestId: 'req-a',
        saved: resultFor('req-a'),
      })
    ).toEqual({ kind: 'fetch', requestId: 'req-b' });
  });

  it('주소에 ID가 있으면 탭에 남은 결과와 같아도 서버에서 받는다', () => {
    expect(
      reportSource({
        ...base,
        urlId: 'req-a',
        savedRequestId: 'req-a',
        saved: resultFor('req-a'),
      })
    ).toEqual({ kind: 'fetch', requestId: 'req-a' });
  });

  it('주소에 ID가 없으면 방금 끝난 분석의 저장된 결과를 쓴다', () => {
    const saved = resultFor('req-a');
    expect(reportSource({ ...base, savedRequestId: 'req-a', saved })).toEqual({
      kind: 'saved',
      result: saved,
    });
  });

  it('요청 ID만 남아 있고 결과가 없으면 그 ID를 서버에서 받는다', () => {
    expect(reportSource({ ...base, savedRequestId: 'req-a' })).toEqual({
      kind: 'fetch',
      requestId: 'req-a',
    });
  });

  it('보여 줄 결과가 없으면 실제 모드는 빈 화면, mock 모드는 미리보기다', () => {
    expect(reportSource(base)).toEqual({ kind: 'empty' });
    expect(reportSource({ ...base, mockMode: true })).toEqual({
      kind: 'preview',
    });
  });

  it('예시 보기로 들어오면 저장된 결과가 있어도 예시를 보여 준다', () => {
    expect(
      reportSource({
        ...base,
        example: true,
        savedRequestId: 'req-a',
        saved: resultFor('req-a'),
      })
    ).toEqual({ kind: 'example' });
  });
});

describe('storedReport', () => {
  it('완료된 요청은 결과와 서버가 나눈 주소·층, 완료일을 돌려준다', () => {
    expect(storedReport(stored({}))).toEqual({
      kind: 'ready',
      result: resultFor('req-b'),
      vacancyInput: {
        roadAddress: '서울특별시 송파구 오금로 404',
        floorUnit: '2층 201호',
      },
      analyzedDate: '2026.10.27',
    });
  });

  it('도로명주소가 없으면 지번주소를, 상세주소가 없으면 빈 층을 쓴다', () => {
    const report = storedReport(
      stored({
        site: {
          input_address: '서울 송파구 오금동 1-1',
          jibun_address: '서울 송파구 오금동 1-1',
        },
      })
    );
    expect(report.kind === 'ready' && report.vacancyInput).toEqual({
      roadAddress: '서울 송파구 오금동 1-1',
      floorUnit: '',
    });
  });

  it('상가 정보가 없으면 요청에 들어온 주소를 그대로 쓴다', () => {
    const fallback = storedReport(stored({ site: null }));
    const nothing = storedReport(
      stored({ site: null, input_address: undefined })
    );
    expect(fallback.kind === 'ready' && fallback.vacancyInput).toEqual({
      roadAddress: '서울 송파구 오금로 404 2층 201호',
      floorUnit: '',
    });
    expect(nothing.kind === 'ready' && nothing.vacancyInput).toBeNull();
  });

  it('아직 끝나지 않은 요청은 진행 중이다', () => {
    for (const status of ['pending', 'running', 'waiting_for_input'] as const) {
      expect(storedReport(stored({ status, result: null }))).toEqual({
        kind: 'pending',
        requestId: 'req-b',
      });
    }
  });

  it('실패한 요청은 서버가 남긴 실패 안내를 그대로 전한다', () => {
    expect(
      storedReport(
        stored({
          status: 'failed',
          result: null,
          error: {
            code: 'INTERRUPTED',
            message: '서버가 다시 시작되었습니다.',
          },
        })
      )
    ).toEqual({ kind: 'failed', message: '서버가 다시 시작되었습니다.' });
  });
});

describe('isExampleReport', () => {
  it('주소에 example이 있으면 예시 리포트다', () => {
    expect(isExampleReport('?example=1')).toBe(true);
    expect(isExampleReport('?id=a&example=1')).toBe(true);
  });

  it('example이 없으면 예시가 아니다', () => {
    expect(isExampleReport('?id=a')).toBe(false);
    expect(isExampleReport('')).toBe(false);
  });
});
