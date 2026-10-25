import Link from 'next/link';
import HeroIllustration from '@/components/landing/HeroIllustration';
import { colors } from '@/styles/tokens';

/**
 * 랜딩 첫 화면 — 서비스 이름 CHAIUM(채움)을 크게 놓고, 그 안의 AI만 채워
 * "AI로 빈 자리를 채운다"는 뜻을 보여준다. 뒤에는 빈 상가가 있는 건물 블록 그림.
 * 헤더는 이 섹션 위에 overlay로 겹쳐 놓는다(app/page.tsx).
 */
export default function Hero() {
  return (
    <section
      className="relative w-full overflow-hidden"
      style={{
        backgroundColor: colors.brand.wash,
        height: 'clamp(640px, 100svh, 940px)',
      }}
    >
      <HeroIllustration className="absolute inset-x-0 bottom-[210px] h-[44%] w-full sm:bottom-10 sm:h-[calc(100%-120px)]" />

      <div className="pointer-events-none absolute inset-x-0 top-[30%] -translate-y-1/2 text-center sm:top-1/2 sm:-translate-y-[58%]">
        {/*
          CHAIUM → CHUM.AI 애니메이션. 동작은 globals.css의 .wordmark 블록 참고.
          보이지 않는 CHUM.AI로 자리 폭을 먼저 잡고 그 왼쪽 끝에 글자를 붙여서,
          AI가 빠지고 붙는 동안 CH는 제자리에 있다.
        */}
        <p
          aria-label="CHAIUM, chum.ai"
          className="wordmark relative inline-block text-left leading-[0.88] font-black tracking-[-0.045em] whitespace-nowrap"
          style={{ fontSize: 'clamp(56px, 14vw, 228px)' }}
        >
          <span aria-hidden="true" className="invisible">
            CHUM.AI
          </span>
          <span
            aria-hidden="true"
            className="wordmark-line absolute top-0 left-0"
          >
            <span className="wordmark-fill">CH</span>
            <span className="wordmark-ai-out">AI</span>
            <span className="wordmark-fill">UM</span>
            <span className="wordmark-ai-in">
              <span className="wordmark-dot">.</span>
              <span className="wordmark-ai-land">AI</span>
            </span>
          </span>
        </p>
      </div>

      <div className="absolute inset-x-4 bottom-[112px] flex flex-col items-start justify-between gap-6 sm:inset-x-10 sm:flex-row sm:items-end">
        <h1
          className="font-extrabold tracking-[-0.05em]"
          style={{
            color: colors.brand.dark,
            fontSize: 'clamp(32px, 4vw, 58px)',
            lineHeight: 1.22,
          }}
        >
          {/* 워드마크가 완성된 뒤 올라오고, 둘째 줄은 파랑이 차오른다(globals.css .slogan 블록) */}
          <span className="slogan-line">
            <span className="slogan-rise">빈 공실에</span>
          </span>
          <span className="slogan-line">
            <span className="slogan-rise slogan-rise-late slogan-fill">
              새로운 가치를 채우다
            </span>
          </span>
        </h1>
        <Link
          href="/vacancy-input"
          className="inline-flex items-center gap-3.5 text-sm font-bold tracking-[0.04em]"
          style={{ color: colors.brand.dark }}
        >
          분석 시작
          <span
            className="inline-flex size-8 items-center justify-center border-[1.5px]"
            style={{ borderColor: colors.brand.dark }}
          >
            <svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true">
              <path
                d="M2 7h10M8 3l4 4-4 4"
                stroke="currentColor"
                strokeWidth="1.8"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </Link>
      </div>
    </section>
  );
}
