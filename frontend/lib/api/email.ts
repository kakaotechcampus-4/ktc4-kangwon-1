/** 가입 화면에서 아이디와 도메인을 따로 받아 하나로 합친다. */

export const EMAIL_DOMAINS = [
  'naver.com',
  'gmail.com',
  'daum.net',
  'kakao.com',
  'nate.com',
  'hanmail.net',
] as const;

/** 목록에 없는 회사·학교 주소를 위해 직접 칠 수 있는 선택지를 남긴다. */
export const CUSTOM_DOMAIN = 'custom';

export function joinEmail(local: string, domain: string): string {
  const trimmedLocal = local.trim();
  const trimmedDomain = domain.trim().replace(/^@/, '');
  if (!trimmedLocal || !trimmedDomain) {
    return '';
  }
  return `${trimmedLocal}@${trimmedDomain}`;
}

// 형식을 엄밀히 따지지 않는다. 진짜 검증은 "메일을 받아 링크를 눌렀는가"이고,
// 과한 정규식은 멀쩡한 주소를 막는다. 백엔드도 같은 기준을 쓴다.
const EMAIL_PATTERN = /^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$/;

export function isEmailLike(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}
