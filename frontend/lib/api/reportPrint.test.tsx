import { afterEach, describe, expect, it, vi } from 'vitest';
import { printReport } from '@/lib/api/reportPrint';

afterEach(() => {
  document.title = '';
  document.body.innerHTML = '';
});

function reportWithDetails() {
  document.body.innerHTML = `
    <div class="report-page">
      <details id="closed"><summary>계산 방법</summary><p>본문</p></details>
      <details id="open" open><summary>원자료</summary><p>본문</p></details>
    </div>
    <details id="outside"><summary>바깥</summary></details>
  `;
  return (id: string) => document.getElementById(id) as HTMLDetailsElement;
}

describe('printReport', () => {
  it('인쇄하는 동안만 PDF 이름을 탭 제목으로 쓰고 끝나면 되돌린다', () => {
    document.title = '채움';
    const seen: string[] = [];
    const print = vi
      .spyOn(window, 'print')
      .mockImplementation(() => seen.push(document.title));
    printReport('채움 업종분석 리포트 - 서울 (2026.11.04)');
    expect(print).toHaveBeenCalledTimes(1);
    expect(seen).toEqual(['채움 업종분석 리포트 - 서울 (2026.11.04)']);
    window.dispatchEvent(new Event('afterprint'));
    expect(document.title).toBe('채움');
  });

  it('리포트 안의 접힌 칸은 인쇄 동안 펼치고 끝나면 원래대로 접는다', () => {
    const details = reportWithDetails();
    const states: boolean[][] = [];
    vi.spyOn(window, 'print').mockImplementation(() => {
      states.push([details('closed').open, details('open').open]);
    });
    printReport('이름');
    expect(states).toEqual([[true, true]]);
    expect(details('outside').open).toBe(false);
    window.dispatchEvent(new Event('afterprint'));
    expect(details('closed').open).toBe(false);
    expect(details('open').open).toBe(true);
  });

  it('인쇄가 끝난 뒤 다른 인쇄에는 다시 손대지 않는다', () => {
    document.title = '채움';
    vi.spyOn(window, 'print').mockImplementation(() => {});
    printReport('이름');
    window.dispatchEvent(new Event('afterprint'));
    document.title = '다른 화면';
    window.dispatchEvent(new Event('afterprint'));
    expect(document.title).toBe('다른 화면');
  });
});
