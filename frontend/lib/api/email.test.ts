import { describe, expect, it } from 'vitest';
import {
  CUSTOM_DOMAIN,
  EMAIL_DOMAINS,
  isEmailLike,
  joinEmail,
} from '@/lib/api/email';

describe('joinEmail', () => {
  it('아이디와 도메인을 합친다', () => {
    expect(joinEmail('kim', 'naver.com')).toBe('kim@naver.com');
  });

  it('앞뒤 공백과 사용자가 덧붙인 @를 정리한다', () => {
    expect(joinEmail('  kim  ', ' @naver.com ')).toBe('kim@naver.com');
  });

  it('한쪽이 비면 빈 문자열이다', () => {
    expect(joinEmail('', 'naver.com')).toBe('');
    expect(joinEmail('kim', '')).toBe('');
  });
});

describe('isEmailLike', () => {
  it('평범한 주소를 통과시킨다', () => {
    for (const value of [
      'kim@naver.com',
      'a.b@company.co.kr',
      'x+tag@gmail.com',
    ]) {
      expect(isEmailLike(value)).toBe(true);
    }
  });

  it('@나 점이 없는 주소를 막는다', () => {
    for (const value of [
      'kim',
      'kim@',
      'kim@naver',
      '@naver.com',
      'a b@c.com',
    ]) {
      expect(isEmailLike(value)).toBe(false);
    }
  });
});

describe('EMAIL_DOMAINS', () => {
  it('직접 입력 값과 겹치지 않는다', () => {
    // 겹치면 셀렉트가 "직접 입력"을 고른 상태와 구분되지 않는다.
    expect(EMAIL_DOMAINS).not.toContain(CUSTOM_DOMAIN);
  });
});
