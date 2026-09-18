import { Outfit, DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type Block = {
  id: string;
  heading: string;
  body: string;
};

export default function AIAnalysisSummary() {
  const {
    exclusionReason,
    recommendationReason,
    favorableConditions,
    synergyTips,
  } = mockReportData.aiAnalysisSummary;

  const blocks: Block[] = [
    {
      id: 'exclusion',
      heading: '왜 이 업종들은 제외했나요',
      body: exclusionReason,
    },
    {
      id: 'recommendation',
      heading: '왜 이 업종이 가장 적합한가요',
      body: recommendationReason,
    },
    {
      id: 'conditions',
      heading: '이런 조건에서 특히 유리해요',
      body: favorableConditions,
    },
    { id: 'synergy', heading: '더 나은 시너지를 위한 팁', body: synergyTips },
  ];

  return (
    <div className="w-full px-8 pt-8">
      <div
        className="w-full rounded-xl p-8"
        style={{ backgroundColor: colors.brand.dark }}
      >
        <p
          className={`${dmMono.className} text-xs tracking-[1.68px] uppercase`}
          style={{ color: colors.brand.primary }}
        >
          AI 분석 요약
        </p>
        <p
          className={`${outfit.className} pt-3 text-[27px] font-bold text-white`}
        >
          추천 업종은 이렇게 정해졌어요
        </p>

        <div className="mt-6 grid w-full grid-cols-2 gap-x-10 gap-y-6">
          {blocks.map((block) => (
            <div key={block.id} className="flex flex-col items-start">
              <h3
                className={`${outfit.className} text-base font-semibold`}
                style={{ color: colors.brand.primary }}
              >
                {block.heading}
              </h3>
              <p className="pt-2 text-sm leading-[24px] text-white/70">
                {block.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
