import { Outfit, DM_Mono } from 'next/font/google';
import {
  Camera,
  Coffee,
  Croissant,
  Dumbbell,
  Flame,
  FlaskConical,
  Mic2,
  Monitor,
  PawPrint,
  Store,
  WashingMachine,
  type LucideIcon,
} from 'lucide-react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import {
  mockReportData,
  type RecommendedIndustry,
} from '@/lib/mockData/report';
import type { IndustryAssessment } from '@/lib/api/types';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
});

const industryIcons: Record<string, LucideIcon> = {
  '네일·뷰티': FlaskConical,
  무인점포: Monitor,
  '소형 스튜디오': Camera,
  코인세탁실: WashingMachine,
  '반려동물 미용': PawPrint,
  고깃집: Flame,
  '대형 카페': Coffee,
  베이커리: Croissant,
  노래방: Mic2,
  헬스장: Dumbbell,
};

/**
 * 이 카드가 실제로 그리는 데 필요한 최소 정보. mockReportData의 임의 구조
 * (RecommendedIndustry: rank/name/tags)와 실제 DecisionResult 스키마
 * (IndustryAssessment: category.major/middle, reasons, evidence, risks)를
 * 하나의 형태로 맞춰서, 렌더링 쪽은 어느 소스에서 왔는지 몰라도 되게 한다.
 */
type DisplayIndustry = {
  rank: number;
  name: string;
  score: number;
  reasons: string[];
  risks: string[];
};

function fromLegacy(item: RecommendedIndustry): DisplayIndustry {
  return {
    rank: item.rank,
    name: item.name,
    score: item.score,
    reasons: item.tags,
    risks: [],
  };
}

function fromAssessment(
  item: IndustryAssessment,
  rank: number
): DisplayIndustry {
  return {
    rank,
    name: item.category.middle,
    score: item.score,
    reasons: item.reasons,
    risks: item.risks,
  };
}

type Column = {
  id: string;
  title: string;
  badgePrefix: string;
  emptyLabel: string;
  tint: string;
  accent: string;
  progressColor: 'primary' | 'danger';
  items: DisplayIndustry[];
};

export default function RecommendationSection({
  recommendations,
  notRecommended,
}: {
  recommendations?: IndustryAssessment[];
  notRecommended?: IndustryAssessment[];
}) {
  const recommendedItems: DisplayIndustry[] = recommendations
    ? recommendations.map((item, i) => fromAssessment(item, i + 1))
    : mockReportData.recommended.map(fromLegacy);
  const notRecommendedItems: DisplayIndustry[] = notRecommended
    ? notRecommended.map((item, i) => fromAssessment(item, i + 1))
    : mockReportData.notRecommended.map(fromLegacy);

  const columns: Column[] = [
    {
      id: 'recommended',
      title: '추천 업종',
      badgePrefix: 'TOP',
      emptyLabel: '추천할 업종이 없습니다.',
      tint: `${colors.brand.primary}1A`,
      accent: colors.brand.primary,
      progressColor: 'primary',
      items: recommendedItems,
    },
    {
      id: 'not-recommended',
      title: '비추천 업종',
      badgePrefix: 'BOTTOM',
      emptyLabel: '비추천 업종이 없습니다.',
      tint: `${colors.status.notRecommend}1A`,
      accent: colors.status.notRecommend,
      progressColor: 'danger',
      items: notRecommendedItems,
    },
  ];

  return (
    <div className="flex w-full items-start gap-6 px-8 pt-8">
      {columns.map((column) => (
        <Card
          key={column.id}
          className="flex-1"
          style={{
            padding: 0,
            borderRadius: '12px',
            borderWidth: '1px',
            boxShadow:
              '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
          }}
        >
          <div
            className="flex w-full items-center justify-between px-6 py-4"
            style={{
              backgroundColor: column.tint,
              borderBottom: `1px solid ${colors.neutral.border}`,
            }}
          >
            <p
              className={`${dmMono.className} text-base tracking-[1.68px] uppercase`}
              style={{ color: column.accent }}
            >
              {column.title}
            </p>
            <Badge
              style={{
                backgroundColor: column.accent,
                color: colors.neutral.white,
                fontSize: '12px',
                letterSpacing: '1.26px',
              }}
            >
              {column.items.length > 0
                ? `${column.badgePrefix} ${column.items.length}`
                : '0건'}
            </Badge>
          </div>

          <div className="flex w-full flex-col gap-6 p-6">
            {column.items.length === 0 && (
              <div className="flex w-full flex-col items-center justify-center gap-1 py-10 text-center">
                <p
                  className="text-sm"
                  style={{ color: 'var(--color-gray-400)' }}
                >
                  {column.emptyLabel}
                </p>
              </div>
            )}
            {column.items.map((item) => {
              const Icon = industryIcons[item.name] ?? Store;

              return (
                <div
                  key={item.rank}
                  className="flex w-full flex-col items-start"
                >
                  <div className="flex w-full items-center gap-3">
                    <p
                      className={`${dmMono.className} shrink-0 text-base`}
                      style={{ color: colors.neutral.border }}
                    >
                      {String(item.rank).padStart(2, '0')}
                    </p>
                    <div
                      className="flex size-11 shrink-0 items-center justify-center rounded-lg"
                      style={{ backgroundColor: column.tint }}
                    >
                      <Icon
                        size={22}
                        strokeWidth={1.75}
                        style={{ color: column.accent }}
                      />
                    </div>
                    <p
                      className={`${outfit.className} text-base font-bold ${
                        column.id === 'recommended' ? '' : 'text-gray-600'
                      }`}
                      style={
                        column.id === 'recommended'
                          ? { color: colors.neutral.black }
                          : undefined
                      }
                    >
                      {item.name}
                    </p>
                    <div className="flex flex-1 items-baseline justify-end gap-1">
                      <p
                        className={`${dmMono.className} text-xl font-medium`}
                        style={{ color: column.accent }}
                      >
                        {item.score}
                      </p>
                      <p className="text-sm text-gray-400">점</p>
                    </div>
                  </div>

                  <div className="w-full pt-2">
                    <ProgressBar
                      value={item.score}
                      color={column.progressColor}
                    />
                  </div>

                  {/*
                    실제 DecisionResult에는 tags 같은 짧은 칩용 필드가 없고
                    reasons(문장)만 있다. 배지 대신 짧은 불릿 목록으로
                    바꿔서, 목업 데이터(RecommendedIndustry.tags)와 실제
                    스키마(IndustryAssessment.reasons) 둘 다 같은 자리에서
                    자연스럽게 보이게 한다. 카드가 길어지지 않도록 상위
                    2개까지만 보여준다.
                  */}
                  <ul
                    className="w-full list-disc pt-2.5 pl-4 text-xs marker:text-gray-300"
                    style={{ color: 'var(--color-gray-500)' }}
                  >
                    {item.reasons.slice(0, 2).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>

                  {/*
                    risks는 목업(RecommendedIndustry)엔 없던 필드라 실제
                    스키마(IndustryAssessment)를 쓸 때만 채워진다. reasons와
                    같은 자리(카드 안)에 두되, 점수를 뒷받침하는 근거와
                    헷갈리지 않도록 앞에 "주의" 라벨을 붙이고 accent 색으로
                    구분한다.
                  */}
                  {item.risks.length > 0 && (
                    <ul
                      className="w-full list-none pt-1.5 text-xs"
                      style={{ color: colors.accent.orange }}
                    >
                      {item.risks.slice(0, 2).map((risk) => (
                        <li key={risk}>주의 · {risk}</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
