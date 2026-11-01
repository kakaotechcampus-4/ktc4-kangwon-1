'use client';

import Input from '@/components/ui/Input';
import { CUSTOM_DOMAIN, EMAIL_DOMAINS } from '@/lib/api/email';
import { colors } from '@/styles/tokens';

type Props = {
  local: string;
  domain: string;
  onLocalChange: (value: string) => void;
  onDomainChange: (value: string) => void;
};

/**
 * 아이디와 도메인을 나눠 받는다. 임대인 사용자에게 익숙한 형태다.
 * 목록에 없는 주소도 쓸 수 있게 "직접 입력"을 반드시 남긴다.
 */
export default function EmailField({
  local,
  domain,
  onLocalChange,
  onDomainChange,
}: Props) {
  const picked = EMAIL_DOMAINS.find((item) => item === domain);
  const mode = picked ?? CUSTOM_DOMAIN;

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor="email-local"
        className="text-15 font-medium text-gray-500"
      >
        이메일
      </label>

      <div className="flex items-center gap-2">
        <Input
          id="email-local"
          name="email_local"
          inputMode="email"
          autoComplete="email"
          required
          placeholder="아이디"
          value={local}
          onChange={(event) => onLocalChange(event.target.value)}
          className="min-w-0 flex-1"
        />
        <span
          className="shrink-0 text-base"
          style={{ color: colors.text.tertiary }}
        >
          @
        </span>
        <select
          aria-label="이메일 도메인 선택"
          value={mode}
          onChange={(event) => {
            const next = event.target.value;
            // 직접 입력으로 바꾸면 칸을 비워 사용자가 바로 칠 수 있게 한다.
            onDomainChange(next === CUSTOM_DOMAIN ? '' : next);
          }}
          className="w-[132px] shrink-0 rounded-xl border-[1.5px] px-3 py-3.5 text-base outline-none focus:border-[#2453D6]"
          style={{
            backgroundColor: colors.neutral.white,
            borderColor: '#D5DEE7',
            color: colors.brand.dark,
          }}
        >
          {EMAIL_DOMAINS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
          <option value={CUSTOM_DOMAIN}>직접 입력</option>
        </select>
      </div>

      {mode === CUSTOM_DOMAIN ? (
        <Input
          name="email_domain"
          required
          placeholder="직접 입력 (예: company.co.kr)"
          aria-label="이메일 도메인 직접 입력"
          value={domain}
          onChange={(event) => onDomainChange(event.target.value)}
        />
      ) : null}
    </div>
  );
}
