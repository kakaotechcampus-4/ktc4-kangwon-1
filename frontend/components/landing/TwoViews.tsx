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
  return (
    <section
      id="services"
      className="relative -mt-10 w-full rounded-t-[40px] bg-white px-4 pt-24 pb-28 sm:px-8"
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="text-center">
          <Eyebrow>HOW WE READ SPACE</Eyebrow>
          <h2 className="mt-3.5 text-4xl font-extrabold tracking-[-0.02em] text-[#111827]">
            건물 안과 밖, 두 가지 시선으로
          </h2>
          <p className="mx-auto mt-4 max-w-[560px] text-base leading-[1.7] text-[#5B6470]">
            공간의 조건을 파악하고, 동네의 흐름을 살펴봅니다. 따로 보면 놓치기
            쉬운 단서를 함께 놓아야 이 자리에 어울리는 업종이 보입니다.
          </p>
        </div>

        <ol className="mt-14 grid gap-5 md:grid-cols-3">
          {views.map(({ number, tag, title, description }) => (
            <li
              key={tag}
              className="flex flex-col rounded-[22px] p-8"
              style={{ backgroundColor: colors.brand.wash }}
            >
              <div className="flex items-center justify-between">
                <span
                  className="rounded-full px-3 py-1 text-13 font-bold text-white"
                  style={{ backgroundColor: colors.brand.primary }}
                >
                  {tag}
                </span>
                <span className="text-sm font-bold text-[#8A97A5]">
                  {number}
                </span>
              </div>
              <h3 className="mt-10 text-22 font-extrabold tracking-[-0.02em] text-[#111827]">
                {title}
              </h3>
              <p className="mt-3 text-15 leading-[1.75] text-[#4B5563]">
                {description}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
