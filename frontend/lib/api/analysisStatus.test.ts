import { describe, expect, it } from 'vitest';
import { analysisLink, formatDay, statusLabel } from '@/lib/api/analysisStatus';

describe('statusLabel', () => {
  it('백엔드 상태 머신의 다섯 상태를 모두 옮긴다', () => {
    // docs/API_CONTRACT.md: pending → running → (waiting_for_input ↔ running)
    //                       → completed | failed
    expect(statusLabel('completed')).toEqual({
      text: '분석 완료',
      tone: 'done',
    });
    expect(statusLabel('running').tone).toBe('running');
    expect(statusLabel('pending').tone).toBe('running');
    expect(statusLabel('waiting_for_input').tone).toBe('waiting');
    expect(statusLabel('failed').tone).toBe('failed');
  });

  it('모르는 상태가 와도 화면이 비지 않는다', () => {
    expect(statusLabel('something_new').text).toBe('something_new');
  });
});

describe('formatDay', () => {
  it('저장된 UTC 문자열을 날짜로 줄인다', () => {
    expect(formatDay('2026-10-27T04:13:05+00:00')).toMatch(
      /^\d{4}\.\d{2}\.\d{2}$/
    );
  });

  it('값이 없거나 깨졌으면 빈 문자열이다', () => {
    expect(formatDay(null)).toBe('');
    expect(formatDay('어제')).toBe('');
  });
});

describe('analysisLink', () => {
  it('완료된 분석은 리포트로 간다', () => {
    expect(analysisLink('a b', 'completed')).toEqual({
      label: '리포트 열기',
      href: '/report?id=a%20b',
    });
  });

  it('답변을 기다리는 분석은 진행 화면으로 돌아간다', () => {
    expect(analysisLink('r1', 'waiting_for_input')).toEqual({
      label: '답변하러 가기',
      href: '/analysis-progress?id=r1',
    });
  });

  it('실패하거나 아직 도는 분석은 버튼이 없다', () => {
    expect(analysisLink('r1', 'failed')).toBeNull();
    expect(analysisLink('r1', 'running')).toBeNull();
  });
});
