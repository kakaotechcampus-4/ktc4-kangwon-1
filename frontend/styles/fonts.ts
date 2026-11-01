import localFont from 'next/font/local';

/**
 * 서비스 전체 글꼴 — Pretendard 가변 글꼴 하나로 한글·영문·숫자를 모두 그린다.
 * 글꼴 파일과 라이선스(SIL OFL 1.1)는 app/fonts/에 함께 둔다.
 * 예전에 섹션마다 따로 쓰던 Outfit·DM Mono 자리도 이 값을 그대로 쓴다.
 */
export const pretendard = localFont({
  src: '../app/fonts/PretendardVariable.woff2',
  variable: '--font-pretendard',
  weight: '45 920',
  display: 'swap',
});
