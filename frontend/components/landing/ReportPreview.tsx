'use client';

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
      className="report-preview-container flex w-full flex-col items-start py-16"
    >
      <div className="flex w-full items-end justify-between">
        <h2
          className={`report-preview-headline ${outfit.className} font-bold`}
          style={{ color: colors.neutral.black }}
        >
          분석 리포트 미리보기
        </h2>
        <button
          type="button"
          className={`rp-cta ${outfit.className} font-semibold`}
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

          className="rp-header flex w-full items-center justify-between"
          style={{
            backgroundColor: colors.brand.dark,
            borderBottom: `1px solid ${colors.neutral.border}`,
          }}
        >
          <div className="flex flex-col items-start">
            <p className={`rp-address ${outfit.className} font-semibold text-white`}>
              강원도 춘천시 후평동 234-5 · 2층
            </p>
            <p className="rp-address-sub pt-0.5 text-white/60">
              전용 26평 · 월세 120만원 · 분석 2026.08.22
            </p>
          </div>
          <Badge
            className="rp-badge"
            style={{
              backgroundColor: colors.brand.primary,
              color: colors.neutral.white,
              letterSpacing: '1.68px',
            }}
          >
            분석 완료
          </Badge>
        </div>

        <div
          className="rp-section flex w-full flex-col items-start"
          style={{ borderBottom: `1px solid ${colors.neutral.border}` }}
        >
          <p
            className={`rp-section-label ${dmMono.className} tracking-[1.68px] uppercase`}

            style={{ color: colors.brand.primary }}
          >
            AI 핵심 결론
          </p>
          <p
            className={`rp-conclusion ${outfit.className} pt-2 font-semibold`}
            style={{ color: colors.neutral.black }}
          >
            이 공실에 가장 적합한 업종은{' '}
            <span style={{ color: colors.brand.primary }}>네일·뷰티</span>{' '}
            업종입니다.
          </p>
          <p className="rp-desc pt-2 text-gray-600">
            전면폭과 급·배수 조건이 양호하며, 반경 500m 내 동일 업종 경쟁점이
            적어 시장 진입 여건이 우수합니다.
          </p>
        </div>

        <div className="rp-ranks flex w-full">
          {ranks.map(({ id, number, label, score }) => (
            <div key={id} className="flex flex-1 flex-col gap-2">
              <div className="flex w-full items-center justify-between">
                <p
                  className="rp-rank-label font-semibold"
                  style={{ color: colors.neutral.black }}
                >
                  {label}
                </p>
                <p
                  className={`rp-rank-score ${dmMono.className} font-medium`}
                  style={{ color: colors.brand.primary }}
                >

                  {score}점
                </p>
              </div>
              <div className="flex w-full items-center gap-4">
                <p
                  className={`rp-rank-number ${dmMono.className} shrink-0`}
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

      {/*
        375px~1337px 단일 clamp 원칙(ProblemCards.tsx / ValueSteps.tsx와 동일
        앵커, divisor=962)을 헤드라인뿐 아니라 카드 내부 요소까지 전부
        확장했다. 각 항목은 원래 Tailwind 고정 크기(text-base=16px,
        text-sm=14px, text-xs=12px, text-[23px]/leading-[27.5px],
        text-[15px], text-lg=18px, px-8=32px, py-5=20px, py-6=24px)를
        1337px 앵커(=기존 데스크톱 값 그대로)로 유지하고, 375px 앵커는
        그 비율에 맞춰 역산했다. Tailwind 쪽 크기 클래스는 전부 제거해
        같은 속성을 두 곳에서 지정하는 충돌을 없앤다.
      */}
      <style jsx global>{`
        .report-preview-container {
          padding-inline: clamp(
            20px,
            calc(20px + (100vw - 375px) * 0.0832),

            100px
          );
        }
        .report-preview-headline {
          --headline-fs: clamp(
            26px,
            calc(26px + (100vw - 375px) * 0.018711),
            44px
          );
          font-size: var(--headline-fs);
          line-height: calc(var(--headline-fs) * 1.13636);
        }
        .rp-cta {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.003119),
            14px
          );
        }
        .rp-header {
          padding-inline: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.016632),
            32px
          );
          padding-block: clamp(
            12px,
            calc(12px + (100vw - 375px) * 0.008316),
            20px
          );
        }
        .rp-address {

          font-size: clamp(
            12px,
            calc(12px + (100vw - 375px) * 0.004158),
            16px
          );
        }
        .rp-address-sub {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.003119),
            14px
          );
        }
        .rp-badge {
          font-size: clamp(
            9px,
            calc(9px + (100vw - 375px) * 0.003119),
            12px
          );
        }
        .rp-section {
          padding-inline: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.016632),
            32px
          );
          padding-block: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.010395),
            24px
          );
        }

        .rp-section-label {
          font-size: clamp(
            9px,
            calc(9px + (100vw - 375px) * 0.003119),
            12px
          );
        }
        .rp-conclusion {
          --rp-conclusion-fs: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.007276),
            23px
          );
          font-size: var(--rp-conclusion-fs);
          line-height: calc(var(--rp-conclusion-fs) * 1.19565);
        }
        .rp-desc {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.004158),
            15px
          );
        }
        .rp-ranks {
          gap: clamp(16px, calc(16px + (100vw - 375px) * 0.010395), 24px);
          padding-inline: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.016632),
            32px
          );
          padding-block: clamp(
            14px,

            calc(14px + (100vw - 375px) * 0.010395),
            24px
          );
        }
        .rp-rank-label {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.003119),
            14px
          );
        }
        .rp-rank-score {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.003119),
            14px
          );
        }
        .rp-rank-number {
          font-size: clamp(
            13px,
            calc(13px + (100vw - 375px) * 0.005199),
            18px
          );
        }
      `}</style>
    </div>
  );
}