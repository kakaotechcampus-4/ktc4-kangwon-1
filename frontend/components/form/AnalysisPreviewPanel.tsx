'use client';

import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

type PreviewItem = {
  id: string;
  dotColor: string;
  title: string;
  description: string;
};

const previewItems: PreviewItem[] = [
  {
    id: 'competitors',
    dotColor: colors.status.recommend,
    title: '경쟁업체 개수',
    description: '반경 500m 내 동일 업종 수 자동 계산',
  },
  {
    id: 'foot-traffic',
    dotColor: colors.brand.dark,
    title: '유동인구 분포',
    description: '시간대·연령대별 유동인구 데이터 연동',
  },
  {
    id: 'open-close',
    dotColor: colors.status.notRecommend,
    title: '개폐업 현황',
    description: '유사 업종 최근 개업·폐업 추이 확인',
  },
];

export default function AnalysisPreviewPanel() {
  return (
    <Card
      className="analysis-preview-card shrink-0 gap-4"
      style={{
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow: 'none',
      }}
    >
      <div className="flex w-full items-start justify-between gap-2">
        <div className="flex flex-col items-start gap-0.5">
          <p
            className="analysis-preview-title font-bold"
            style={{ color: colors.neutral.black }}
          >
            주소만 입력하면, 이렇게 분석돼요
          </p>
          <p className="analysis-preview-subtitle text-gray-500">
            AI 판독 확인 이후 자동으로 연동됩니다
          </p>
        </div>
        <span className="analysis-preview-badge shrink-0 rounded-md bg-gray-100 px-2 py-1 font-bold text-gray-500">
          예시
        </span>
      </div>

      <div
        className="h-px w-full"
        style={{ backgroundColor: colors.neutral.border }}
      />

      <div className="flex w-full flex-col items-start gap-4">
        {previewItems.map(({ id, dotColor, title, description }) => (
          <div key={id} className="flex w-full items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: dotColor }}
              />
            </div>
            <div className="flex flex-1 flex-col items-start gap-0.5">
              <p
                className="analysis-preview-item-title font-medium"
                style={{ color: colors.neutral.black }}
              >
                {title}
              </p>
              <p className="analysis-preview-item-desc text-gray-500">
                {description}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/*
        폭/패딩/폰트 크기를 Tailwind 클래스와 병행하지 않고 이 블록
        하나에서만 관리한다(같은 속성을 두 소스가 동시에 지정하면 우선순위
        충돌이 발생했던 전례가 있어, Hero.tsx 등에서 확립한 방식을 따름).

        768px 미만(모바일): AddressInput과 세로로 쌓이므로 카드 폭은 기본
        규칙(width:100%)을 유지하고, 폰트/패딩은 기존 데스크톱 값을 그대로
        사용한다(이 구간은 축소 대상이 아님).

        768px~1024px(태블릿): 가로 배치로 전환되면서 카드 폭·내부
        padding·폰트 크기를 AddressInput 대비 상대적으로 작게 줄인다.
        하나의 @media(min-width:768px) 블록 안에서 clamp()로 768px→
        230px(최소)~1024px→360px(기존값, 최대)를 선형 보간하므로:
        - 768.0px 진입 시점에도 값이 끊기지 않고
        - 1024px 이상에서는 clamp 상한이 기존 w-[360px]/22px 24px/
          17·12·11·14·12px 폰트와 정확히 같은 값에서 고정되어 데스크톱
          레이아웃이 그대로 유지된다(별도 1024px 미디어 쿼리 불필요).
      */}
      <style jsx global>{`
        .analysis-preview-card {
          width: 100%;
          padding-block: 22px;
          padding-inline: 24px;
        }
        .analysis-preview-title {
          font-size: 17px;
        }
        .analysis-preview-subtitle {
          font-size: 12px;
        }
        .analysis-preview-badge {
          font-size: 11px;
        }
        .analysis-preview-item-title {
          font-size: 14px;
        }
        .analysis-preview-item-desc {
          font-size: 12px;
        }

        @media (min-width: 768px) {
          .analysis-preview-card {
            width: clamp(230px, calc(230px + (100vw - 768px) * 0.507812), 360px);
            padding-block: clamp(
              14px,
              calc(14px + (100vw - 768px) * 0.03125),
              22px
            );
            padding-inline: clamp(
              16px,
              calc(16px + (100vw - 768px) * 0.03125),
              24px
            );
          }
          .analysis-preview-title {
            font-size: clamp(
              14px,
              calc(14px + (100vw - 768px) * 0.011719),
              17px
            );
          }
          .analysis-preview-subtitle {
            font-size: clamp(
              10px,
              calc(10px + (100vw - 768px) * 0.007812),
              12px
            );
          }
          .analysis-preview-badge {
            font-size: clamp(
              9px,
              calc(9px + (100vw - 768px) * 0.007812),
              11px
            );
          }
          .analysis-preview-item-title {
            font-size: clamp(
              12px,
              calc(12px + (100vw - 768px) * 0.007812),
              14px
            );
          }
          .analysis-preview-item-desc {
            font-size: clamp(
              10px,
              calc(10px + (100vw - 768px) * 0.007812),
              12px
            );
          }
        }
      `}</style>
    </Card>
  );
}
