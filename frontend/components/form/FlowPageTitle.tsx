import { colors } from '@/styles/tokens';

/**
 * 분석 흐름 화면(공실 입력 · 상가 정보 확인 · 분석 진행)의 공통 제목 묶음.
 * 파란 영문 라벨 + 굵은 제목 + 설명. 화면마다 같은 모양이 되도록 한곳에 둔다.
 */
export default function FlowPageTitle({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p
        className="text-sm font-bold tracking-[0.08em]"
        style={{ color: colors.brand.primary }}
      >
        {eyebrow}
      </p>
      <h1
        className="font-extrabold tracking-[-0.04em] break-keep"
        style={{
          color: colors.brand.dark,
          fontSize: 'clamp(30px, 3.4vw, 46px)',
          lineHeight: 1.25,
        }}
      >
        {title}
      </h1>
      <p className="text-base leading-relaxed text-[#4B5866]">{description}</p>
    </div>
  );
}
