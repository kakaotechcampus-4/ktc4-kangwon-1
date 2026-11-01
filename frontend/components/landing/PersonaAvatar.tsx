import { useId } from 'react';

/**
 * 상황 예시 카드의 인물 아바타(직접 그린 일러스트). 특정 인물이 아니라
 * "이런 상황의 건물주"를 나타내는 장식이라 보조기기에는 숨긴다.
 */
export default function PersonaAvatar({ size = 64 }: { size?: number }) {
  // 카드가 여러 장이라 그라데이션 id가 겹치지 않게 아바타마다 접두어를 붙인다.
  const uid = useId().replace(/:/g, '');
  const id = (name: string) => `${uid}-${name}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      aria-hidden="true"
      className="shrink-0"
    >
      <defs>
        <radialGradient id={id('pa-bg')} cx="0.35" cy="0.3" r="0.8">
          <stop offset="0" stopColor="#E8EEFC" />
          <stop offset="1" stopColor="#CCD8F6" />
        </radialGradient>
        <radialGradient id={id('pa-skin')} cx="0.4" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#FCE3D2" />
          <stop offset="1" stopColor="#EFC2A6" />
        </radialGradient>
        <linearGradient id={id('pa-hair')} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9A6A4C" />
          <stop offset="1" stopColor="#6E4632" />
        </linearGradient>
        <linearGradient id={id('pa-shirt')} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E3E8F2" />
        </linearGradient>
        <clipPath id={id('pa-clip')}>
          <circle cx="48" cy="48" r="48" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id('pa-clip')})`}>
        <rect width="96" height="96" fill={`url(#${id('pa-bg')})`} />
        {/* 뒷머리 */}
        <path
          d="M24 46c0-17 10-28 24-28s24 11 24 28v20H24z"
          fill={`url(#${id('pa-hair')})`}
        />
        {/* 어깨·셔츠 */}
        <path
          d="M14 96c2-16 15-24 34-24s32 8 34 24z"
          fill={`url(#${id('pa-shirt')})`}
        />
        {/* 목 */}
        <path d="M41 62h14v12a7 7 0 0 1-14 0z" fill="#EBB99B" />
        {/* 스카프 */}
        <path d="M38 72l10 6 10-6 3 6-13 7-13-7z" fill="#2453D6" />
        <path d="M45 79l3 10 3-10z" fill="#173A9C" />
        {/* 얼굴 */}
        <ellipse
          cx="48"
          cy="46"
          rx="17"
          ry="19"
          fill={`url(#${id('pa-skin')})`}
        />
        {/* 귀 */}
        <ellipse cx="31" cy="48" rx="3" ry="4.5" fill="#EFC2A6" />
        <ellipse cx="65" cy="48" rx="3" ry="4.5" fill="#EFC2A6" />
        {/* 앞머리 */}
        <path
          d="M30 44c0-14 8-21 18-21 11 0 19 7 19 19-6-1-12-5-15-11-4 7-12 12-22 13z"
          fill={`url(#${id('pa-hair')})`}
        />
        {/* 눈·눈썹 */}
        <ellipse cx="41.5" cy="48" rx="2.2" ry="2.8" fill="#3A2A22" />
        <ellipse cx="54.5" cy="48" rx="2.2" ry="2.8" fill="#3A2A22" />
        <circle cx="42.2" cy="47" r="0.8" fill="#FFFFFF" />
        <circle cx="55.2" cy="47" r="0.8" fill="#FFFFFF" />
        <path
          d="M38 42.5q3.5-2 7 0M51 42.5q3.5-2 7 0"
          stroke="#6E4632"
          strokeWidth="1.6"
          fill="none"
          strokeLinecap="round"
        />
        {/* 볼·코·입 */}
        <ellipse
          cx="37.5"
          cy="54"
          rx="3.2"
          ry="2"
          fill="#F4A9A0"
          opacity="0.6"
        />
        <ellipse
          cx="58.5"
          cy="54"
          rx="3.2"
          ry="2"
          fill="#F4A9A0"
          opacity="0.6"
        />
        <path
          d="M47 51.5q1 2.5 2 0"
          stroke="#D9967A"
          strokeWidth="1.4"
          fill="none"
          strokeLinecap="round"
        />
        <path
          d="M44 57q4 3.5 8 0"
          stroke="#B4594F"
          strokeWidth="1.8"
          fill="none"
          strokeLinecap="round"
        />
      </g>
    </svg>
  );
}
