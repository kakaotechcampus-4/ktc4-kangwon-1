import type { Metadata } from 'next';
import NoticePage from '@/components/layout/NoticePage';
import StateNotice from '@/components/ui/StateNotice';

export const metadata: Metadata = {
  title: '채움 · 페이지를 찾을 수 없어요',
};

export default function NotFoundPage() {
  return (
    <NoticePage
      eyebrow="PAGE NOT FOUND"
      title="찾는 페이지가 없어요"
      description="주소가 바뀌었거나 없어진 페이지예요."
    >
      <StateNotice
        title="이렇게 해 보세요"
        description="홈에서 공실 분석을 새로 시작하거나, 내 분석 기록에서 지난 리포트를 열어 보세요."
        links={[
          { href: '/', label: '홈으로' },
          { href: '/my/reports', label: '내 분석 기록' },
        ]}
      />
    </NoticePage>
  );
}
