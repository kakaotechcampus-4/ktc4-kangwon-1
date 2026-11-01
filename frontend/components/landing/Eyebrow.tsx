/** 섹션 제목 위 작은 영문 라벨. 어두운 바탕에서는 tone="dark". */
export default function Eyebrow({
  children,
  tone = 'light',
}: {
  children: string;
  tone?: 'light' | 'dark';
}) {
  return (
    <p
      className={`text-sm font-bold tracking-[0.08em] ${
        tone === 'dark' ? 'text-[#9DB5F2]' : 'text-[#2453D6]'
      }`}
    >
      {children}
    </p>
  );
}
