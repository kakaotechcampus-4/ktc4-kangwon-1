import type { ReactNode } from 'react';
import { Outfit, DM_Mono } from 'next/font/google';
import {
  ChevronsDown,
  TrendingUp,
  ChartNoAxesCombined,
  Info,
  Camera,
  Coffee,
  Croissant,
  Dumbbell,
  Flame,
  FlaskConical,
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
import { industryEmoji } from '@/lib/report/industryEmoji';
import type { Evidence, IndustryAssessment } from '@/lib/api/types';

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
  필라테스: Dumbbell,
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
  evidence: Evidence[];
};

function formatTrendLabel(label: string): string {
  if (/[↑↓]/.test(label)) return label;
  if (/하락|감소/.test(label)) return `${label} ↓`;
  if (/증가|상승/.test(label)) return `${label} ↑`;
  if (/순증감\s*\+/.test(label)) return `${label} ↑`;
  if (/순증감\s*-/.test(label)) return `${label} ↓`;
  return label;
}

function isAnalysisLabel(label: string): boolean {
  // 자료의 상태는 남기고, 입점 전에 확인하거나 검토할 조건만 숨긴다.
  if (/자료|판단 보류/.test(label)) return true;
  return !/확인|검토|필요/.test(label);
}

function fromLegacy(item: RecommendedIndustry): DisplayIndustry {
  return {
    rank: item.rank,
    name: item.name,
    score: item.score,
    reasons: item.tags.filter(isAnalysisLabel),
    risks: [],
    evidence: [],
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
    reasons: item.reasons.filter(isAnalysisLabel),
    risks: item.risks,
    evidence: item.evidence,
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
  children,
  showEmoji = false,
}: {
  children?: ReactNode;
  recommendations?: IndustryAssessment[];
  notRecommended?: IndustryAssessment[];
  showEmoji?: boolean;
}) {
  const recommendedItems: DisplayIndustry[] = recommendations
    ? recommendations.map((item, i) => fromAssessment(item, i + 1))
    : mockReportData.recommended.map(fromLegacy);
  const notRecommendedItems: DisplayIndustry[] = (
    notRecommended
      ? notRecommended.map((item, i) => fromAssessment(item, i + 1))
      : mockReportData.notRecommended.map(fromLegacy)
  )
    .sort((a, b) => a.score - b.score)
    .map((item, index) => ({ ...item, rank: index + 1 }));

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
    <div id="industry-recommendations" className="w-full px-8 pt-8">
      <div className="mb-6 flex items-center justify-between gap-8">
        <h2 className="shrink-0 text-2xl font-bold text-gray-900">
          내 공실에 어떤 업종이 적합할까요?
        </h2>
        <aside
          className="relative rounded-xl bg-[#EAF5F3] py-3 pr-5 pl-6"
          aria-label="점수 안내"
        >
          <span
            className="absolute top-4 bottom-4 left-0 w-1 rounded-r-full bg-[#008C80]"
            aria-hidden="true"
          />
          <div className="flex items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[#008C80] text-white">
              <TrendingUp size={21} aria-hidden="true" />
            </span>
            <div>
              <p className="text-base leading-6 font-bold text-[#006B65]">
                점수가 높을수록 이 상가에 더 적합해요
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-sm leading-5 text-gray-600">
                <ChartNoAxesCombined
                  size={14}
                  className="shrink-0"
                  aria-hidden="true"
                />
                예상 매출·창업 성공 확률은 아니에요
              </p>
            </div>
          </div>
        </aside>
      </div>
      <div className="flex w-full items-start gap-6">
        {columns.map((column) => (
          <Card
            key={column.id}
            className="min-w-0 flex-1"
            style={{
              padding: 0,
              overflow: 'visible',
              borderRadius: '12px',
              borderWidth: '1px',
              boxShadow:
                '0px 2px 8px 0px rgba(0,0,0,0.04), 0px 10px 30px 0px rgba(0,0,0,0.06)',
            }}
          >
            <div
              className="flex w-full items-center justify-between rounded-t-[11px] px-6 py-4"
              style={{
                backgroundColor: column.accent,
                borderBottom: `1px solid ${colors.neutral.border}`,
              }}
            >
              <div className="flex items-center gap-2">
                <p
                  className={`${dmMono.className} text-base tracking-[1.68px] uppercase`}
                  style={{ color: colors.neutral.white }}
                >
                  {column.title}
                </p>
                {column.id === 'not-recommended' && (
                  <div className="group relative flex items-center">
                    <button
                      type="button"
                      aria-label="비추천 업종의 의미 안내"
                      aria-describedby="not-recommended-info"
                      className="rounded-full text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
                    >
                      <Info size={20} aria-hidden="true" />
                    </button>
                    <div
                      id="not-recommended-info"
                      role="tooltip"
                      className="invisible absolute bottom-full left-1/2 z-20 w-80 -translate-x-1/2 pb-3 opacity-0 transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                    >
                      <p className="rounded-xl border border-gray-200 bg-white p-4 text-sm leading-6 text-gray-700 shadow-lg">
                        비추천은{' '}
                        <strong className="font-bold text-[#C52F40]">
                          입점 불가가 아니에요
                        </strong>
                        . 법적 제한은{' '}
                        <a
                          href="#school-regulation"
                          className="font-semibold text-[#006B65] underline underline-offset-4"
                        >
                          학교 주변 규제
                        </a>{' '}
                        등에서 별도로 확인하세요.
                      </p>
                      <span
                        aria-hidden="true"
                        className="absolute bottom-2 left-1/2 size-3 -translate-x-1/2 rotate-45 border-r border-b border-gray-200 bg-white"
                      />
                    </div>
                  </div>
                )}
              </div>
              <Badge
                style={{
                  backgroundColor: 'rgba(255,255,255,0.18)',
                  color: colors.neutral.white,
                  fontSize: 'var(--text-xs)',
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
                    <div className="grid h-[120px] w-full grid-cols-[minmax(0,1fr)_auto_170px] grid-rows-[1fr_8px] items-center gap-x-4 gap-y-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <p
                          className={`${dmMono.className} shrink-0 text-base`}
                          style={{ color: '#8491A3' }}
                        >
                          {String(item.rank).padStart(2, '0')}
                        </p>
                        <div
                          className="flex size-11 shrink-0 items-center justify-center rounded-lg"
                          style={{ backgroundColor: column.tint }}
                        >
                          {showEmoji ? (
                            <span aria-hidden="true" className="text-2xl">
                              {industryEmoji(item.name)}
                            </span>
                          ) : (
                            <Icon
                              size={22}
                              strokeWidth={1.75}
                              style={{ color: column.accent }}
                            />
                          )}
                        </div>
                        <p
                          className={`${outfit.className} text-xl font-bold ${
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
                      </div>
                      <div className="flex shrink-0 items-baseline gap-1">
                        <p
                          className={`${dmMono.className} text-3xl font-medium`}
                          style={{ color: column.accent }}
                        >
                          {item.score}
                        </p>
                        <p className="text-sm text-gray-400">점</p>
                      </div>
                      <ul
                        className="row-span-2 grid h-[120px] min-w-0 grid-cols-1 content-center justify-items-stretch gap-1.5"
                        aria-label={`${item.name} 판단 근거`}
                      >
                        {item.reasons.map((reason, index) => (
                          <li
                            key={`${index}-${reason}`}
                            className="flex h-9 items-center justify-start rounded-xl px-3 py-1.5 text-left text-[13px] break-keep leading-5 font-medium"
                            style={{
                              backgroundColor: /자료|신뢰도|판단 보류/.test(
                                reason
                              )
                                ? '#E2E7ED'
                                : column.id === 'recommended'
                                  ? '#D2EAE5'
                                  : '#FADADF',
                              color: /자료|신뢰도|판단 보류/.test(reason)
                                ? '#526071'
                                : column.id === 'recommended'
                                  ? '#006B65'
                                  : '#B73343',
                            }}
                          >
                            {formatTrendLabel(reason)}
                          </li>
                        ))}
                      </ul>

                      <div className="col-span-2 w-full self-end">
                        <ProgressBar
                          value={item.score}
                          color={column.progressColor}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        ))}
      </div>
      {children}
      <div className="flex justify-center pt-16 pb-12" aria-hidden="true">
        <ChevronsDown
          size={48}
          strokeWidth={2.5}
          className="animate-bounce text-[#006B65] motion-reduce:animate-none"
        />
      </div>
    </div>
  );
}
