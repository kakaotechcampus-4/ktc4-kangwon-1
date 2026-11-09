'use client';

import NoticePage from '@/components/layout/NoticePage';
import StateNotice from '@/components/ui/StateNotice';

export default function ErrorPage({ retry }: { retry: () => void }) {
  return (
    <NoticePage
      eyebrow="SOMETHING WENT WRONG"
      title="화면을 여는 중에 문제가 생겼어요"
      description="잠시 후 다시 시도해 주세요."
    >
      <StateNotice
        title="다시 시도해 주세요"
        description="같은 문제가 계속되면 홈에서 다시 시작해 주세요."
        links={[{ href: '/', label: '홈으로' }]}
        onRetry={retry}
        retryLabel="다시 시도"
      />
    </NoticePage>
  );
}
