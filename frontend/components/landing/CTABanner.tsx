'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { saveVacancyInput } from '@/lib/api/resultStore';
import { colors } from '@/styles/tokens';

/**
 * 랜딩 마지막 — 주소만 받아 바로 상가 정보 확인 화면으로 보낸다.
 * 층·호수와 반경은 비워 두면 다음 단계에서 기본값과 질문으로 채운다
 * (공실 입력 화면의 "지금 다 채울 필요는 없어요" 흐름과 같다).
 */
export default function CTABanner() {
  const router = useRouter();
  const [address, setAddress] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!address.trim()) {
      alert('주소를 입력해주세요');
      return;
    }
    saveVacancyInput({
      roadAddress: address.trim(),
      floorUnit: '',
      radius: '',
    });
    router.push('/building-confirm');
  }

  return (
    <section className="w-full px-4 py-26 sm:px-8">
      <div
        className="mx-auto flex max-w-[1120px] flex-col gap-8 rounded-[28px] px-8 py-14 sm:px-12 sm:py-16 lg:flex-row lg:items-center lg:justify-between"
        style={{ backgroundColor: colors.brand.primary }}
      >
        <div>
          <h2 className="text-34 leading-[1.35] font-extrabold tracking-[-0.02em] text-white">
            이 자리의 다음을
            <br />
            찾아볼까요?
          </h2>
          <p className="mt-3.5 text-base text-[#DCE6FF]">
            상가 주소를 입력해 분석을 시작해 보세요.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex w-full flex-wrap gap-2.5 rounded-2xl bg-white p-2 lg:max-w-[480px]"
        >
          <label htmlFor="landing-address" className="sr-only">
            분석할 상가 주소
          </label>
          <input
            id="landing-address"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="예) 서울시 강동구 길동 ○○로 12"
            className="h-12 min-w-[180px] flex-1 bg-transparent px-3 text-base outline-none placeholder:text-[#8A97A5]"
            style={{ color: colors.brand.dark }}
          />
          <button
            type="submit"
            className="inline-flex h-12 items-center gap-2 rounded-xl px-5 text-base font-extrabold text-[#1B2A33] transition-opacity hover:opacity-90"
            style={{ backgroundColor: '#F2B84B' }}
          >
            분석 시작
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path
                d="M2 7h10M8 3l4 4-4 4"
                stroke="currentColor"
                strokeWidth="1.8"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </form>
      </div>
    </section>
  );
}
