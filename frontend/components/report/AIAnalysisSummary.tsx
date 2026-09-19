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

/**
 * 실제 DecisionResult에는 "이런 조건에서 특히 유리해요"/"더 나은 시너지를
 * 위한 팁"에 해당하는 필드가 없다(summary 한 줄 + 업종별 reasons/risks
 * 배열뿐). 무리해서 4분면을 다 채우지 않고, 실제로 뜻이 통하는 두 블록만
 * 만든다:
 *   - "왜 이 업종들은 제외했나요" ← not_recommended[0].reasons
 *   - "왜 이 업종이 가장 적합한가요" ← recommendations[0].reasons
 * recommendations/not_recommended는 최대 5개일 뿐 최소 개수 제약이 없어
 * (backend/app/schemas.py DecisionContent) 둘 다 빈 배열일 수 있다 — 그
 * 경우 매핑되는 블록 자체를 생략한다.
 */
export default function AIAnalysisSummary({
  summary,
  recommendedReasons,
  notRecommendedReasons,
}: {
  summary?: string;
  recommendedReasons?: string[];
  notRecommendedReasons?: string[];
} = {}) {
  const isReal =
    summary !== undefined ||
    recommendedReasons !== undefined ||
    notRecommendedReasons !== undefined;

  const blocks: Block[] = isReal
    ? [
        ...(notRecommendedReasons && notRecommendedReasons.length > 0
          ? [
              {
                id: 'exclusion',
                heading: '왜 이 업종들은 제외했나요',
                body: notRecommendedReasons.join(' '),
              },
            ]
          : []),
        ...(recommendedReasons && recommendedReasons.length > 0
          ? [
              {
                id: 'recommendation',
                heading: '왜 이 업종이 가장 적합한가요',
                body: recommendedReasons.join(' '),
              },
            ]
          : []),
      ]
    : [
        {
          id: 'exclusion',
          heading: '왜 이 업종들은 제외했나요',
          body: mockReportData.aiAnalysisSummary.exclusionReason,
        },
        {
          id: 'recommendation',
          heading: '왜 이 업종이 가장 적합한가요',
          body: mockReportData.aiAnalysisSummary.recommendationReason,
        },
        {
          id: 'conditions',
          heading: '이런 조건에서 특히 유리해요',
          body: mockReportData.aiAnalysisSummary.favorableConditions,
        },
        {
          id: 'synergy',
          heading: '더 나은 시너지를 위한 팁',
          body: mockReportData.aiAnalysisSummary.synergyTips,
        },
      ];

  // summary는 결정 에이전트가 왜 이렇게 판단했는지를 한 문장으로 요약한
  // 것이라, 이 자리(기존엔 고정 문구였던 헤드라인)에 그대로 쓰는 게 가장
  // 자연스럽다.
  const headline =
    isReal && summary ? summary : '추천 업종은 이렇게 정해졌어요';

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
          {headline}
        </p>

        {blocks.length > 0 && (
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
        )}
      </div>
    </div>
  );
}
