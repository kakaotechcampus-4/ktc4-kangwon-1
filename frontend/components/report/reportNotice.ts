import type { NoticeLink } from '@/components/ui/StateNotice';
import { AnalysisApiError } from '@/lib/api/analyses';

export type ReportNoticeState =
  | { kind: 'empty' }
  | { kind: 'loading' }
  | { kind: 'pending'; requestId: string }
  | { kind: 'failed'; message: string; onRetry?: () => void };

const MY_REPORTS: NoticeLink = { href: '/my/reports', label: '내 분석 기록' };

export function reportNotice(state: ReportNoticeState): {
  title: string;
  description: string;
  links: NoticeLink[];
  onRetry?: () => void;
  busy: boolean;
} {
  switch (state.kind) {
    case 'empty':
      return {
        title: '아직 볼 리포트가 없어요',
        description:
          '공실 분석을 마치면 여기에서 리포트를 볼 수 있어요. 지난 분석은 내 분석 기록에서 열 수 있어요.',
        links: [
          { href: '/vacancy-input', label: '공실 분석 시작하기' },
          MY_REPORTS,
        ],
        busy: false,
      };
    case 'loading':
      return {
        title: '리포트를 불러오고 있어요',
        description: '',
        links: [],
        busy: true,
      };
    case 'pending':
      return {
        title: '아직 분석이 끝나지 않았어요',
        description: '분석이 끝나면 이 리포트를 볼 수 있어요.',
        links: [
          {
            href: `/analysis-progress?id=${encodeURIComponent(state.requestId)}`,
            label: '진행 상황 보기',
          },
          MY_REPORTS,
        ],
        busy: false,
      };
    case 'failed':
      return {
        title: '리포트를 보여 드릴 수 없어요',
        description: state.message,
        links: [MY_REPORTS],
        onRetry: state.onRetry,
        busy: false,
      };
  }
}

export function fetchFailed(
  error: unknown,
  retry: () => void
): ReportNoticeState {
  if (error instanceof AnalysisApiError && error.status === 404) {
    return { kind: 'failed', message: error.message };
  }
  return {
    kind: 'failed',
    message:
      error instanceof Error ? error.message : '리포트를 불러오지 못했어요.',
    onRetry: retry,
  };
}
