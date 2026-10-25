import { Eyebrow } from '@/components/landing/ServiceSection';

// 실제 화면 흐름(주소 입력 → 상가 정보 확인 → 분석 진행 → 리포트)을 세 단계로 묶었다.
const steps = [
  {
    number: '01',
    title: '공실 정보 입력',
    description: '주소와 층·호수를 넣고, 불러온 건물 정보를 확인합니다.',
  },
  {
    number: '02',
    title: 'AI 상권 분석',
    description: '유동인구·경쟁업체·개폐업 데이터를 교차 분석합니다.',
  },
  {
    number: '03',
    title: '리포트 확인',
    description: 'AI 핵심 결론과 추천 업종을 한 장의 리포트로 받아봅니다.',
  },
];

export default function HowItWorks() {
  return (
    <section id="how" className="w-full bg-[#F5F7F9] px-4 py-26 sm:px-8">
      <div className="mx-auto max-w-[1120px]">
        <div className="text-center">
          <Eyebrow>HOW IT WORKS</Eyebrow>
          <h2 className="mt-3.5 text-4xl font-extrabold tracking-[-0.02em] text-[#111827]">
            세 단계면 충분합니다
          </h2>
        </div>
        <ol className="mt-14 grid gap-5 md:grid-cols-3">
          {steps.map(({ number, title, description }) => (
            <li key={number} className="rounded-[20px] bg-white p-8">
              <p className="text-sm font-bold text-[#2453D6]">{number}</p>
              <p className="mt-4.5 text-xl font-extrabold text-[#111827]">
                {title}
              </p>
              <p className="mt-2.5 text-15 leading-[1.7] text-[#4B5563]">
                {description}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
