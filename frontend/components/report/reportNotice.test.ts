import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { fetchFailed, reportNotice } from '@/components/report/reportNotice';
import { AnalysisApiError } from '@/lib/api/analyses';
import StateNotice from '@/components/ui/StateNotice';

const hrefs = (state: Parameters<typeof reportNotice>[0]) =>
  reportNotice(state).links.map((link) => link.href);

describe('reportNotice', () => {
  it('볼 결과가 없으면 분석 시작과 내 분석 기록으로 보낸다', () => {
    expect(hrefs({ kind: 'empty' })).toEqual(['/vacancy-input', '/my/reports']);
  });

  it('아직 진행 중이면 그 요청의 진행 화면으로 보낸다', () => {
    expect(hrefs({ kind: 'pending', requestId: 'req b/1' })).toEqual([
      '/analysis-progress?id=req%20b%2F1',
      '/my/reports',
    ]);
  });

  it('받는 중에는 이동할 곳 없이 상태만 알린다', () => {
    const notice = reportNotice({ kind: 'loading' });
    expect(notice.links).toEqual([]);
    expect(notice.busy).toBe(true);
  });

  it('실패하면 서버 안내를 보여 주고, 다시 받을 수 있을 때만 다시 시도를 둔다', () => {
    const retry = vi.fn();
    const withRetry = reportNotice({
      kind: 'failed',
      message: '서버에 연결하지 못했어요.',
      onRetry: retry,
    });
    const withoutRetry = reportNotice({
      kind: 'failed',
      message: '서버가 다시 시작되었습니다.',
    });
    expect(withRetry.description).toBe('서버에 연결하지 못했어요.');
    expect(withRetry.onRetry).toBe(retry);
    expect(withoutRetry.onRetry).toBeUndefined();
    expect(withoutRetry.links.map((link) => link.href)).toContain(
      '/my/reports'
    );
  });
});

describe('fetchFailed', () => {
  it('없는 요청(404)은 다시 받아도 같으므로 다시 시도를 두지 않는다', () => {
    const notice = fetchFailed(
      new AnalysisApiError(404, '분석 요청을 찾을 수 없습니다.'),
      vi.fn()
    );
    expect(notice).toEqual({
      kind: 'failed',
      message: '분석 요청을 찾을 수 없습니다.',
    });
  });

  it('연결 오류는 다시 시도할 수 있다', () => {
    const retry = vi.fn();
    const notice = fetchFailed(new TypeError('Failed to fetch'), retry);
    expect(notice.kind === 'failed' && notice.onRetry).toBe(retry);
  });
});

describe('StateNotice', () => {
  it('이동 링크와 다시 시도 버튼을 그린다', () => {
    const html = renderToStaticMarkup(
      createElement(StateNotice, {
        title: '제목',
        description: '설명',
        links: [{ href: '/my/reports', label: '내 분석 기록' }],
        onRetry: () => {},
      })
    );
    expect(html).toContain('href="/my/reports"');
    expect(html).toContain('<button');
  });

  it('받는 중이면 화면 읽기 프로그램에 상태로 알린다', () => {
    const html = renderToStaticMarkup(
      createElement(StateNotice, {
        title: '불러오는 중',
        description: '',
        links: [],
        busy: true,
      })
    );
    expect(html).toContain('role="status"');
    expect(html).not.toContain('<button');
  });
});
