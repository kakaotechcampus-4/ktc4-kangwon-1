import Image from 'next/image';
import Link from 'next/link';
import { colors } from '@/styles/tokens';

/**
 * 랜딩 첫 화면 — 서비스 이름 CHAIUM(채움)을 크게 놓고, 그 안의 AI만 채워
 * "AI로 빈 자리를 채운다"는 뜻을 보여준다. 뒤에는 빈 상가가 있는 건물 블록 그림
 * (public/images/hero-blocks.svg — 디자인 캔버스 A안 '소프트 아이소메트릭'), 왼쪽 위·오른쪽 위에 꾸밈용 파란 동심원.
 * 이전 그림(HeroIllustration.tsx)은 되돌릴 때를 위해 파일로 남겨 둔다.
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
      {/* 꾸밈용 파란 원 — 겹친 동심원 세 겹과 가운데 은은한 빛(globals.css .hero-orb) */}
      <span
        aria-hidden="true"
        className="hero-orb pointer-events-none absolute -top-[120px] -left-[160px] size-[440px] sm:-top-[140px] sm:-left-[180px] sm:size-[560px]"
      />
      <span
        aria-hidden="true"
        className="hero-orb hero-orb-late pointer-events-none absolute top-[4%] right-[-360px] hidden size-[720px] sm:block lg:right-[-380px] lg:size-[780px]"
      />
      <Image
        src="/images/hero-blocks.svg"
        alt="연한 하늘색 지붕을 얹은 흰 건물 블록과 나무가 있는 아이소메트릭 그림"
        width={1440}
        height={900}
        priority
        unoptimized
        className="pointer-events-none absolute inset-x-0 bottom-[260px] h-[36%] w-full object-contain object-bottom select-none sm:bottom-12 sm:h-[calc(100%-72px)]"
      />

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
        {/* 파란 알약 버튼 — 오른쪽 흰 원 안의 화살표가 마우스를 올리면 살짝 앞으로 나간다. */}
        <Link
          href="/vacancy-input"
          className="group inline-flex h-14 items-center gap-4 rounded-full py-2 pr-2 pl-7 text-base font-bold text-white shadow-[0_12px_28px_rgba(36,83,214,0.32)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_16px_34px_rgba(36,83,214,0.4)]"
          style={{ backgroundColor: colors.brand.primary }}
        >
          분석 시작하기
          <span className="inline-flex size-10 items-center justify-center rounded-full bg-white">
            <svg
              width="16"
              height="16"
              viewBox="0 0 14 14"
              aria-hidden="true"
              className="transition-transform duration-200 group-hover:translate-x-0.5"
              style={{ color: colors.brand.primary }}
            >
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
