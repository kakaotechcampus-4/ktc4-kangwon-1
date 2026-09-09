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
      className="w-[360px] shrink-0 gap-4"
      style={{
        padding: '22px 24px',
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow: 'none',
      }}
    >
      <div className="flex w-full items-start justify-between gap-2">
        <div className="flex flex-col items-start gap-0.5">
          <p
            className="text-[17px] font-bold"
            style={{ color: colors.neutral.black }}
          >
            주소만 입력하면, 이렇게 분석돼요
          </p>
          <p className="text-xs text-gray-500">
            AI 판독 확인 이후 자동으로 연동됩니다
          </p>
        </div>
        <span className="shrink-0 rounded-md bg-gray-100 px-2 py-1 text-[11px] font-bold text-gray-500">
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
                className="text-sm font-medium"
                style={{ color: colors.neutral.black }}
              >
                {title}
              </p>
              <p className="text-xs text-gray-500">{description}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
