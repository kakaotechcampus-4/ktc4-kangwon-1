/** 백엔드 요청 상태를 화면 문구와 색 역할로 옮긴다. */
export type StatusTone = 'done' | 'running' | 'waiting' | 'failed';

const LABELS: Record<string, { text: string; tone: StatusTone }> = {
  completed: { text: '분석 완료', tone: 'done' },
  running: { text: '분석 중', tone: 'running' },
  pending: { text: '대기 중', tone: 'running' },
  waiting_for_input: { text: '추가 답변 필요', tone: 'waiting' },
  failed: { text: '실패', tone: 'failed' },
};

export function statusLabel(status: string): {
  text: string;
  tone: StatusTone;
} {
  return LABELS[status] ?? { text: status, tone: 'running' };
}

/** 2026-10-27T04:13:05+00:00 → 2026.10.27 */
export function formatDay(value: string | null): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }
  const month = `${parsed.getMonth() + 1}`.padStart(2, '0');
  const day = `${parsed.getDate()}`.padStart(2, '0');
  return `${parsed.getFullYear()}.${month}.${day}`;
}
