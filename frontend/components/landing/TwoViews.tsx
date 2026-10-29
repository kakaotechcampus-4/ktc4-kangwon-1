'use client';

import { useEffect, useRef, type CSSProperties } from 'react';
import { ChevronDown } from 'lucide-react';
import Eyebrow from '@/components/landing/Eyebrow';
import { colors } from '@/styles/tokens';

// 채움이 공간을 보는 순서 — 건물 안(공간) → 건물 밖(주변) → 둘을 합친 추천.
const views = [
  {
    number: '01',
    tag: '공간',
    title: '점포의 조건부터',
    description:
      '면적과 층수, 전면 형태 등 업종 선택에 필요한 공간 정보를 살펴봅니다.',
  },
  {
    number: '02',
    tag: '주변',
    title: '동네의 흐름까지',
    description:
      '유동인구와 주변 업종, 개폐업 흐름을 더해 고객과 경쟁 점포의 맥락을 이해합니다.',
  },
  {
    number: '03',
    tag: '추천',
    title: '어울리는 이유를 함께',
    description:
      '후보 업종을 비교하고, 어떤 조건이 추천으로 이어졌는지 근거와 함께 보여드립니다.',
  },
];

export default function TwoViews() {
  const listRef = useRef<HTMLOListElement>(null);

  // 카드 묶음이 화면에 들어오면 한 장씩 차례로 떠오르게 한다(globals.css .view-card).
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (!('IntersectionObserver' in window)) {
      list.dataset.visible = 'true';
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          list.dataset.visible = 'true';
          observer.disconnect();
        }
      },
      { threshold: 0.25 }
    );
    observer.observe(list);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="w-full" style={{ backgroundColor: colors.brand.wash }}>
      <section
        id="services"
        className="relative mx-0 mt-0 w-full rounded-[28px] border border-[#EEF1F4] bg-white px-4 pt-7 pb-8 shadow-none sm:-mt-14 sm:rounded-t-[72px] sm:rounded-b-none sm:border-0 sm:px-8 sm:pt-10 sm:pb-28"
      >
        {/* 모바일에서 다음 내용을 안내하는 이중 스크롤 화살표 */}
        <a
          href="#how-we-read"
          className="scroll-cue mx-auto flex w-fit flex-col items-center"
          aria-label="아래로 내려 채움이 공간을 보는 방법 보기"
        >
          <ChevronDown size={36} strokeWidth={2.6} aria-hidden="true" />
          <ChevronDown size={36} strokeWidth={2.6} aria-hidden="true" />
        </a>
        <div
          id="how-we-read"
          className="mx-auto mt-8 max-w-[1120px] scroll-mt-24 sm:mt-14"
        >
          <div className="text-center">
            <Eyebrow>HOW WE READ SPACE</Eyebrow>
            <h2 className="mt-3.5 text-3xl font-extrabold tracking-[-0.02em] text-[#111827] sm:text-4xl">
              건물 안과 밖, 두 가지 시선으로
            </h2>
            <p className="mx-auto mt-4 max-w-[560px] text-base leading-[1.7] text-[#5B6470]">
              공간의 조건을 파악하고, 동네의 흐름을 살펴봅니다. 따로 보면 놓치기
              쉬운 단서를 함께 놓아야 이 자리에 어울리는 업종이 보입니다.
            </p>
          </div>

          <ol
            ref={listRef}
            data-visible="false"
            className="view-cards mt-9 grid gap-4 sm:mt-14 sm:gap-5 md:grid-cols-3"
          >
            {views.map(({ number, tag, title, description }, index) => (
              <li
                key={tag}
                className="view-card flex flex-col rounded-[22px] p-6 sm:p-8"
                style={
                  {
                    backgroundColor: colors.brand.wash,
                    '--i': index,
                  } as CSSProperties
                }
              >
                <div className="flex items-center justify-between gap-3 sm:hidden">
                  <h3 className="text-xl font-extrabold tracking-[-0.02em] text-[#111827]">
                    {title}
                  </h3>
                  <span
                    className="shrink-0 rounded-full px-3 py-1 text-13 font-bold text-white"
                    style={{ backgroundColor: colors.brand.primary }}
                  >
                    {tag}
                  </span>
                </div>
                <div className="hidden items-center justify-between sm:flex">
                  <span
                    className="rounded-full px-3 py-1 text-13 font-bold text-white"
                    style={{ backgroundColor: colors.brand.primary }}
                  >
                    {tag}
                  </span>
                  <span className="view-card-number text-sm font-bold text-[#8A97A5]">
                    {number}
                  </span>
                </div>
                <h3 className="mt-10 hidden text-22 font-extrabold tracking-[-0.02em] text-[#111827] sm:block">
                  {title}
                </h3>
                <p className="mt-3 text-sm leading-[1.75] text-[#4B5563] sm:text-15">
                  {description}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}
