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
  body: string | string[];
};

export default function AIAnalysisSummary({
  summary,
  recommendedReasons,
  recommendedCategoryName,
  notRecommendedReasons,
  notRecommendedCategoryName,
}: {
  summary?: string;
  recommendedReasons?: string[];
  recommendedCategoryName?: string;
  notRecommendedReasons?: string[];
  notRecommendedCategoryName?: string;
} = {}) {
  const isReal =
    summary !== undefined ||
    recommendedReasons !== undefined ||
    notRecommendedReasons !== undefined;

  const blocks: Block[] = isReal
    ? [
      // reasons 각 문장이 어떤 업종 얘기인지 알 수 있도록 헤딩에
      // category.middle(업종명)을 넣는다. 이름이 안 넘어온 경우를
      // 대비해 폴백 문구도 둔다.
      ...(recommendedReasons && recommendedReasons.length > 0
        ? [
          {
            id: 'recommendation',
            heading: recommendedCategoryName
              ? `왜 ${recommendedCategoryName}이 가장 적합한가요`
              : '왜 이 업종이 가장 적합한가요',
            body: recommendedReasons,
          },
        ]
        : []),
      ...(notRecommendedReasons && notRecommendedReasons.length > 0
        ? [
          {
            id: 'exclusion',
            heading: notRecommendedCategoryName
              ? `왜 ${notRecommendedCategoryName}을 제외했나요`
              : '왜 이 업종을 제외했나요',
            body: notRecommendedReasons,
          },
        ]
        : []),

    ]
    : [
      { id: 'exclusion', heading: '왜 이 업종들은 제외했나요', body: mockReportData.aiAnalysisSummary.exclusionReason },
      { id: 'recommendation', heading: '왜 이 업종이 가장 적합한가요', body: mockReportData.aiAnalysisSummary.recommendationReason },
      { id: 'conditions', heading: '이런 조건에서 특히 유리해요', body: mockReportData.aiAnalysisSummary.favorableConditions },
      { id: 'synergy', heading: '더 나은 시너지를 위한 팁', body: mockReportData.aiAnalysisSummary.synergyTips },
    ];

  // headline은 고정 타이틀로 두고, summary(자유 서술 문단)는 길이가
  // 매번 달라 제목 자리에 넣으면 어색하므로 아래 별도 문단으로 분리한다.
  const headline = '추천 업종은 이렇게 정해졌어요';
  const summaryText = isReal ? summary : undefined;

  return (
    <div className="w-full px-8 pt-8">
      <div className="w-full rounded-xl p-8" style={{ backgroundColor: colors.brand.dark }}>
        <p className={`${dmMono.className} text-xs tracking-[1.68px] uppercase`} style={{ color: colors.brand.primary }}>
          AI 분석 요약
        </p>
        <p className={`${outfit.className} pt-3 text-[27px] font-bold text-white`}>
          {headline}
        </p>

        {summaryText && (
          <p className="pt-3 text-sm leading-[24px] text-white/70">
            {summaryText}
          </p>
        )}

        {blocks.length > 0 && (
          <div className="mt-6 grid w-full grid-cols-2 gap-x-10 gap-y-6">
            {blocks.map((block) => (
              <div key={block.id} className="flex flex-col items-start">
                <h3 className={`${outfit.className} text-base font-semibold`} style={{ color: colors.brand.primary }}>
                  {block.heading}
                </h3>
                {Array.isArray(block.body) ? (
                  <ul className="pt-2 flex flex-col gap-1.5">
                    {block.body.map((line, i) => (
                      <li key={i} className="text-sm leading-[24px] text-white/70">
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="pt-2 text-sm leading-[24px] text-white/70">
                    {block.body}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
