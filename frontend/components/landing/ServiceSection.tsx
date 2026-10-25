import { colors } from '@/styles/tokens';

/**
 * "리포트에 무엇이 나오는지" 미리 보여주는 소개 섹션.
 * 실제 데이터가 아니라 리포트 구성을 설명하는 자리라 업종 이름은 예시 표기다.
 */
const exampleBars = [
  { label: '업종 A', width: '86%' },
  { label: '업종 B', width: '72%' },
  { label: '업종 C', width: '61%' },
];

const collapsedCards = [
  { tag: 'FOOT TRAFFIC', title: '유동인구' },
  { tag: 'COMPETITION', title: '경쟁업체' },
  { tag: 'OPEN · CLOSE', title: '개폐업 추이' },
];

function Eyebrow({ children }: { children: string }) {
  return (
    <p
      className="text-sm font-bold tracking-[0.08em]"
      style={{ color: colors.brand.primary }}
    >
      {children}
    </p>
  );
}

export { Eyebrow };

export default function ServiceSection() {
  return (
    <section
      id="services"
      className="relative -mt-10 w-full rounded-t-[40px] bg-white px-4 pt-24 pb-28 sm:px-8"
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="text-center">
          <Eyebrow>OUR SERVICE</Eyebrow>
          <h2 className="mt-3.5 text-4xl font-extrabold tracking-[-0.02em] text-[#111827]">
            데이터로 공실의 답을 찾습니다
          </h2>
          <p className="mx-auto mt-4 max-w-[520px] text-base leading-[1.7] text-[#5B6470]">
            채움은 상권 데이터를 네 가지 관점으로 나눠 분석하고, 건물주가 바로
            판단할 수 있는 결론으로 정리합니다.
          </p>
        </div>

        <div className="mt-14 flex flex-col gap-3.5">
          <article
            className="flex flex-col gap-8 rounded-[22px] p-6 sm:p-9 md:flex-row md:items-stretch"
            style={{ backgroundColor: colors.brand.wash }}
          >
            <div className="flex flex-1 flex-col justify-center">
              <span
                className="self-start rounded-full px-2.5 py-1 text-11 font-bold tracking-[0.08em] text-white"
                style={{ backgroundColor: colors.brand.primary }}
              >
                RECOMMEND
              </span>
              <h3 className="mt-4 text-27 font-extrabold tracking-[-0.01em] text-[#111827]">
                추천 · 비추천 업종
              </h3>
              <p className="mt-3.5 max-w-[440px] text-15 leading-[1.75] text-[#3F4A55]">
                중분류 업종 기준으로 이 자리에 잘 맞는 업종 TOP 3와 피해야 할
                업종 BOTTOM 3를 근거와 함께 보여드립니다.
              </p>
            </div>
            <div className="flex w-full flex-col justify-center gap-3.5 rounded-2xl bg-white p-6 md:w-[440px]">
              {exampleBars.map(({ label, width }) => (
                <div key={label} className="flex items-center gap-3">
                  <span className="w-16 text-13 text-[#5B6470]">[{label}]</span>
                  <div className="h-3 flex-1 rounded-md bg-[#EEF2F5]">
                    <div
                      className="h-3 rounded-md"
                      style={{ width, backgroundColor: colors.brand.primary }}
                    />
                  </div>
                </div>
              ))}
              <div className="h-px bg-[#E3E8EC]" />
              <div className="flex items-center gap-3">
                <span className="w-16 text-13 text-[#5B6470]">[업종 X]</span>
                <div className="h-3 flex-1 rounded-md bg-[#EEF2F5]">
                  <div className="h-3 w-[24%] rounded-md bg-[#C2CCD4]" />
                </div>
              </div>
            </div>
          </article>

          {collapsedCards.map(({ tag, title }) => (
            <div
              key={tag}
              className="flex h-[100px] items-center justify-between gap-4 rounded-[18px] px-8 text-white"
              style={{ backgroundColor: '#2B4778' }}
            >
              <div>
                <span className="rounded-full bg-white/15 px-2 py-1 text-11 font-bold tracking-[0.08em]">
                  {tag}
                </span>
                <p className="mt-2.5 text-22 font-extrabold">{title}</p>
              </div>
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                aria-hidden="true"
              >
                <path
                  d="M5 8l5 5 5-5"
                  stroke="#ffffff"
                  strokeWidth="2"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
