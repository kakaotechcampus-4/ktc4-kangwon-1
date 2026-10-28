'use client';

import { kakaoLoginUrl } from '@/lib/api/auth';
import { colors } from '@/styles/tokens';

/**
 * fetch가 아니라 주소창 이동이어야 한다. 쿠키는 백엔드가 직접 심으므로
 * 브라우저가 실제로 백엔드로 이동해야 하고, 그 뒤 카카오 동의 화면이 뜬다.
 * next/link는 미리 불러오기 때문에 쓰지 않는다.
 */
export default function KakaoButton({ next }: { next: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        window.location.href = kakaoLoginUrl(next);
      }}
      className="inline-flex w-full items-center justify-center gap-2 rounded-xl px-[28px] py-[14px] text-sm font-bold transition-opacity hover:opacity-90"
      style={{
        backgroundColor: colors.kakao.yellow,
        color: colors.kakao.label,
      }}
    >
      <KakaoMark />
      카카오로 시작하기
    </button>
  );
}

function KakaoMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="currentColor"
        d="M9 1.5C4.86 1.5 1.5 4.14 1.5 7.4c0 2.07 1.37 3.89 3.44 4.94l-.87 3.2c-.08.28.23.5.47.34l3.84-2.54c.2.02.41.03.62.03 4.14 0 7.5-2.64 7.5-5.97S13.14 1.5 9 1.5Z"
      />
    </svg>
  );
}
