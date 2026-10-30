import Image from 'next/image';

/**
 * 유동인구 유형(주거생활형·직장인형·여가상업형 등)에 맞춘 장식용 그림.
 * 라벨 문자열로 그림을 고르고, 알 수 없는 유형은 여가상업형 그림으로 둔다.
 * 정보는 옆 문장이 모두 전달하므로 대체 텍스트는 비워 둔다.
 * 원본: chum-space-site/prototypes/assets/area-type-*-v2.png (여백을 잘라 webp로 변환)
 */
const SCENES = {
  residential: {
    src: '/images/area-types/residential.webp',
    width: 720,
    height: 427,
  },
  office: { src: '/images/area-types/office.webp', width: 720, height: 405 },
  commercial: {
    src: '/images/area-types/commercial.webp',
    width: 720,
    height: 391,
  },
} as const;

export default function AreaTypeIllustration({ label }: { label: string }) {
  const scene = /주거|생활/.test(label)
    ? SCENES.residential
    : /직장|오피스|업무/.test(label)
      ? SCENES.office
      : SCENES.commercial;
  return (
    <Image
      className="area-type-illustration"
      src={scene.src}
      width={scene.width}
      height={scene.height}
      alt=""
      aria-hidden="true"
      sizes="(max-width: 900px) 220px, 280px"
    />
  );
}
