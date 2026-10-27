import Image from 'next/image';
import Link from 'next/link';
import { colors } from '@/styles/tokens';

/**
 * 랜딩 첫 화면 — 왼쪽에 CHAIUM → CHUM.AI 워드마크와 슬로건, 오른쪽에 상권 지도
 * 일러스트(가운데 분석 대상 건물 + 반경 + 주변 데이터 핀)를 둔다.
 * 헤더는 이 섹션 위에 overlay로 겹쳐 놓는다(app/page.tsx).
 * 이전 건물 블록 그림(HeroIllustration)은 되돌릴 때를 위해 파일로 남겨 둔다.
 */
export default function Hero() {
  return (
    <section
      className="relative w-full overflow-hidden"
      style={{
        // 지도 그림의 바탕색과 같게 맞춰 그림 가장자리가 보이지 않게 한다.
        backgroundColor: '#E8F1F8',
        minHeight: 'clamp(640px, 100svh, 940px)',
      }}
    >
      <Image
        src="/images/hero-map.webp"
        alt="가운데 분석 대상 건물에 핀이 꽂히고, 그 둘레 반경 안 상가들에 데이터 표시가 달린 아이소메트릭 상권 지도"
        width={1376}
        height={768}
        priority
        sizes="(max-width: 1024px) 100vw, 72vw"
        style={{
          // 그림 가장자리를 바탕색으로 서서히 녹여 사각형 테두리가 보이지 않게 한다.
          maskImage:
            'radial-gradient(ellipse 72% 70% at 52% 50%, #000 62%, transparent 100%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 72% 70% at 52% 50%, #000 62%, transparent 100%)',
        }}
        className="pointer-events-none absolute right-0 bottom-6 w-full max-w-none select-none lg:top-1/2 lg:bottom-auto lg:w-[72%] lg:max-w-[1180px] lg:-translate-y-[44%]"
      />

      <div className="relative z-10 mx-auto flex min-h-[inherit] max-w-[1440px] flex-col justify-start gap-7 px-5 pt-28 pb-[62vw] sm:px-10 lg:justify-center lg:pt-24 lg:pb-24">
        <div className="pointer-events-none">
          {/*
            CHAIUM → CHUM.AI 애니메이션. 동작은 globals.css의 .wordmark 블록 참고.
            보이지 않는 CHUM.AI로 자리 폭을 먼저 잡고 그 왼쪽 끝에 글자를 붙여서,
            AI가 빠지고 붙는 동안 CH는 제자리에 있다.
          */}
          <p
            aria-label="CHAIUM, chum.ai"
            className="wordmark relative inline-block text-left leading-[0.88] font-black tracking-[-0.045em] whitespace-nowrap"
            style={{ fontSize: 'clamp(56px, 9.4vw, 148px)' }}
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
        <h1
          className="font-extrabold tracking-[-0.05em]"
          style={{
            color: colors.brand.dark,
            fontSize: 'clamp(30px, 3.3vw, 48px)',
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
        <p className="max-w-[420px] text-base leading-[1.75] text-[#4B5866] sm:text-17">
          주소를 넣으면 반경 안 유동인구·경쟁 점포·개폐업 흐름을 읽어 이 자리에
          어울리는 업종을 찾아드려요.
        </p>
        {/* 파란 알약 버튼 — 오른쪽 흰 원 안의 화살표가 마우스를 올리면 살짝 앞으로 나간다. */}
        <Link
          href="/vacancy-input"
          className="group inline-flex h-14 w-fit items-center gap-4 rounded-full py-2 pr-2 pl-7 text-base font-bold text-white shadow-[0_12px_28px_rgba(36,83,214,0.32)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_16px_34px_rgba(36,83,214,0.4)]"
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
