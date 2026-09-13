import { DM_Mono } from 'next/font/google';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

const HIGHLIGHT_PHRASE = '네일·뷰티, 무인점포, 소형 스튜디오';

export default function AISummaryBanner() {
  const { aiSummary } = mockReportData;
  const highlightIndex = aiSummary.indexOf(HIGHLIGHT_PHRASE);
  const before =
    highlightIndex >= 0 ? aiSummary.slice(0, highlightIndex) : aiSummary;
  const after =
    highlightIndex >= 0
      ? aiSummary.slice(highlightIndex + HIGHLIGHT_PHRASE.length)
      : '';

  return (
    <div className="w-full px-8 pt-8">
      <div
        className="w-full rounded-xl p-8"
        style={{ backgroundColor: colors.brand.dark }}
      >
        <p
          className={`${dmMono.className} text-base tracking-[1.68px] uppercase`}
          style={{ color: colors.brand.primary }}
        >
          AI 종합 판단
        </p>
        <p
          className="pt-4 text-base leading-[26px]"
          style={{ color: colors.neutral.white }}
        >
          {before}
          {highlightIndex >= 0 && (
            <span
              className="font-semibold"
              style={{ color: colors.brand.primary }}
            >
              {HIGHLIGHT_PHRASE}
            </span>
          )}
          {after}
        </p>
      </div>
    </div>
  );
}
