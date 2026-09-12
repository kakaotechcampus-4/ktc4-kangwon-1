import { Outfit, DM_Mono } from 'next/font/google';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['600', '700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

type Rank = {
  id: string;
  number: string;
  label: string;
  score: number;
};

const defaultRanks: Rank[] = [
  { id: 'nail-beauty', number: '01', label: '네일·뷰티', score: 92 },
  { id: 'unmanned-store', number: '02', label: '무인점포', score: 87 },
  { id: 'small-studio', number: '03', label: '소형 스튜디오', score: 82 },
];

type ReportPreviewProps = {
  ranks?: Rank[];
};

export default function ReportPreview({
  ranks = defaultRanks,
}: ReportPreviewProps) {
  return (
    <div
      id="report-preview"
      className="flex w-full flex-col items-start px-5 py-12 sm:px-8 lg:px-[100px] lg:py-16"
    >
      <div className="flex w-full flex-col items-start justify-between gap-3 sm:flex-row sm:items-end">
        <h2
          className={`${outfit.className} text-[28px] font-bold sm:text-[36px] lg:text-[44px]`}
          style={{ color: colors.neutral.black }}
        >
          분석 리포트 미리보기
        </h2>
        <button
          type="button"
          className={`${outfit.className} text-sm font-semibold`}
          style={{ color: colors.brand.dark }}
        >
          전체 리포트 보기 →
        </button>
      </div>

      <Card
        className="mt-8 w-full"
        style={{ padding: 0, borderRadius: '12px' }}
      >
        <div
          className="flex w-full flex-col items-start justify-between gap-3 px-5 py-5 sm:flex-row sm:items-center sm:px-8"
          style={{
            backgroundColor: colors.brand.dark,
            borderBottom: `1px solid ${colors.neutral.border}`,
          }}
        >
          <div className="flex flex-col items-start">
            <p
              className={`${outfit.className} text-base font-semibold text-white`}
            >
              강원도 춘천시 후평동 234-5 · 2층
            </p>
            <p className="pt-0.5 text-sm text-white/60">
              전용 26평 · 월세 120만원 · 분석 2026.08.22
            </p>
          </div>
          <Badge
            style={{
              backgroundColor: colors.brand.primary,
              color: colors.neutral.white,
              fontSize: '12px',
              letterSpacing: '1.68px',
            }}
          >
            분석 완료
          </Badge>
        </div>

        <div
          className="flex w-full flex-col items-start px-5 py-6 sm:px-8"
          style={{ borderBottom: `1px solid ${colors.neutral.border}` }}
        >
          <p
            className={`${dmMono.className} text-xs tracking-[1.68px] uppercase`}
            style={{ color: colors.brand.primary }}
          >
            AI 핵심 결론
          </p>
          <p
            className={`${outfit.className} pt-2 text-[23px] leading-[27.5px] font-semibold`}
            style={{ color: colors.neutral.black }}
          >
            이 공실에 가장 적합한 업종은{' '}
            <span style={{ color: colors.brand.primary }}>네일·뷰티</span>{' '}
            업종입니다.
          </p>
          <p className="pt-2 text-[15px] text-gray-600">
            전면폭과 급·배수 조건이 양호하며, 반경 500m 내 동일 업종 경쟁점이
            적어 시장 진입 여건이 우수합니다.
          </p>
        </div>

        <div className="grid w-full grid-cols-1 gap-6 px-5 py-6 md:grid-cols-3 sm:px-8">
          {ranks.map(({ id, number, label, score }) => (
            <div key={id} className="flex flex-1 flex-col gap-2">
              <div className="flex w-full items-center justify-between">
                <p
                  className="text-sm font-semibold"
                  style={{ color: colors.neutral.black }}
                >
                  {label}
                </p>
                <p
                  className={`${dmMono.className} text-sm font-medium`}
                  style={{ color: colors.brand.primary }}
                >
                  {score}점
                </p>
              </div>
              <div className="flex w-full items-center gap-4">
                <p
                  className={`${dmMono.className} shrink-0 text-lg`}
                  style={{ color: colors.neutral.border }}
                >
                  {number}
                </p>
                <ProgressBar value={score} className="flex-1" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
