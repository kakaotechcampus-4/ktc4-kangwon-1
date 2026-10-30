'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Check } from 'lucide-react';
import Eyebrow from '@/components/landing/Eyebrow';
import { colors } from '@/styles/tokens';

/**
 * 리포트가 "왜 이 업종인지"를 어떻게 보여주는지 미리 보는 섹션.
 * 실제 분석 결과가 아니라 표현 방식 예시라서 카드 아래에 그 사실을 적어 둔다.
 */
const examples = [
  {
    industry: '네일 · 뷰티',
    reasons: [
      {
        title: '자연광이 드는 실내',
        detail: '밝은 공간은 시술 환경을 편안하게 구성하는 데 도움이 돼요.',
      },
      {
        title: '거리에서 보이는 전면',
        detail: '유리창을 통해 매장 분위기를 전하기 좋아요.',
      },
      {
        title: '공간 활용의 유연성',
        detail: '시술석과 상담 공간을 나누는 구성을 검토할 수 있어요.',
      },
    ],
  },
  {
    industry: '카페',
    reasons: [
      {
        title: '오가는 사람이 많은 길목',
        detail: '지나가다 들르는 손님을 기대할 수 있는 자리예요.',
      },
      {
        title: '머물기 좋은 넓이',
        detail: '좌석을 여유 있게 두고 오래 머무는 손님을 받을 수 있어요.',
      },
      {
        title: '창가 자리를 만들 수 있는 전면',
        detail: '바깥이 보이는 좌석은 매장을 알리는 역할도 해요.',
      },
    ],
  },
  {
    industry: '쇼룸',
    reasons: [
      {
        title: '넓게 트인 바닥',
        detail: '제품을 여유 있게 놓아 보여주는 구성에 잘 맞아요.',
      },
      {
        title: '눈에 띄는 진열창',
        detail: '대표 제품을 밖에서도 보이게 진열할 수 있어요.',
      },
      {
        title: '예약 방문에 맞는 동선',
        detail: '상담과 체험 공간을 나눠 손님을 맞을 수 있어요.',
      },
    ],
  },
];

export default function ReportPreview() {
  const [active, setActive] = useState(0);
  const [hasEnteredView, setHasEnteredView] = useState(false);
  const reasonsRef = useRef<HTMLOListElement>(null);
  const current = examples[active];

  useEffect(() => {
    const reasons = reasonsRef.current;
    if (!reasons || hasEnteredView) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasEnteredView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
    );

    observer.observe(reasons);
    return () => observer.disconnect();
  }, [hasEnteredView]);

  return (
    <section
      id="report-preview"
      className="w-full px-4 py-26 sm:px-8"
      style={{ backgroundColor: colors.brand.dark }}
    >
      <div className="mx-auto flex max-w-[1120px] flex-col gap-12 lg:flex-row lg:items-center lg:justify-between">
        <div className="lg:max-w-[420px]">
          <Eyebrow tone="dark">REPORT PREVIEW</Eyebrow>
          <h2 className="mt-3.5 text-4xl leading-[1.3] font-extrabold tracking-[-0.02em] text-white">
            “왜 이 업종인가요?”
            <br />
            이유가 보여야 하니까
          </h2>
          <p className="mt-5 text-base leading-[1.8] text-[#C3CCD8]">
            추천 업종을 골라 보세요. 공간의 어떤 점이 그 업종과 맞는지, 리포트가
            보여주는 방식을 미리 확인할 수 있어요.
          </p>
        </div>

        <div className="w-full overflow-hidden rounded-[22px] bg-white lg:max-w-[620px]">
          <div className="flex items-center justify-between border-b border-[#E2E8EE] px-7 py-6">
            <p className="text-17 font-extrabold text-[#111827]">
              이 공간에 어울리는 업종
            </p>
            <p className="text-13 text-[#5B6672]">화면 구성 예시</p>
          </div>

          <div className="px-7 pt-6 pb-2">
            <div
              role="tablist"
              aria-label="예시 업종"
              className="flex flex-wrap gap-2"
            >
              {examples.map(({ industry }, index) => {
                const selected = index === active;
                return (
                  <button
                    key={industry}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => setActive(index)}
                    className={`h-11 rounded-full px-5 text-15 font-semibold transition-colors ${
                      selected
                        ? 'text-white'
                        : 'bg-[#EEF2F5] text-[#3F4A55] hover:bg-[#E2E8EE]'
                    }`}
                    style={
                      selected
                        ? { backgroundColor: colors.brand.primary }
                        : undefined
                    }
                  >
                    {industry}
                  </button>
                );
              })}
            </div>

            <ol
              ref={reasonsRef}
              key={current.industry}
              role="tabpanel"
              aria-label={`${current.industry} 추천 이유`}
            >
              {current.reasons.map(({ title, detail }, index) => (
                <li
                  key={title}
                  className={`report-preview-reason flex items-center gap-5 py-5 ${
                    hasEnteredView ? 'report-preview-reason--visible' : ''
                  } ${index > 0 ? 'border-t border-[#E2E8EE]' : ''}`}
                  style={
                    {
                      '--report-preview-delay': `${index * 220}ms`,
                    } as CSSProperties
                  }
                >
                  <span className="w-6 text-sm font-bold text-[#8A97A5]">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <div className="flex-1">
                    <p className="text-base font-bold text-[#111827]">
                      {title}
                    </p>
                    <p className="mt-1 text-sm text-[#5B6672]">{detail}</p>
                  </div>
                  <span
                    className="flex size-7 shrink-0 items-center justify-center rounded-full"
                    style={{ backgroundColor: colors.brand.wash }}
                  >
                    <Check
                      aria-hidden="true"
                      size={16}
                      strokeWidth={2.5}
                      color={colors.brand.primary}
                    />
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <p className="bg-[#F5F8FB] px-7 py-4 text-13 text-[#5B6672]">
            * 실제 분석 데이터가 아닌, 추천 이유를 보여주는 방식의 예시예요.
          </p>
        </div>
      </div>
    </section>
  );
}
