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

type Column = {
  id: string;
  title: string;
  badgeLabel: string;
  tint: string;
  accent: string;
  tagBg: string;
  tagColor: string;
  progressColor: 'primary' | 'danger';
  items: RecommendedIndustry[];
};

const columns: Column[] = [
  {
    id: 'recommended',
    title: '추천 업종',
    badgeLabel: 'TOP 5',
    tint: `${colors.brand.primary}1A`,
    accent: colors.brand.primary,
    tagBg: `${colors.brand.primary}1A`,
    tagColor: colors.brand.dark,
    progressColor: 'primary',
    items: mockReportData.recommended,
  },
  {
    id: 'not-recommended',
    title: '비추천 업종',
    badgeLabel: 'BOTTOM 5',
    tint: `${colors.status.notRecommend}1A`,
    accent: colors.status.notRecommend,
    tagBg: `${colors.status.notRecommend}1A`,
    tagColor: colors.status.notRecommend,
    progressColor: 'danger',
    items: mockReportData.notRecommended,
  },
];

export default function RecommendationSectionV2() {
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
              {column.badgeLabel}
            </Badge>
          </div>

          <div className="flex w-full flex-col gap-6 p-6">
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

                  <div className="flex w-full flex-wrap gap-1.5 pt-2.5">
                    {item.tags.map((tag) => (
                      <Badge
                        key={tag}
                        style={{
                          backgroundColor: column.tagBg,
                          color: column.tagColor,
                          fontFamily: 'inherit',
                          textTransform: 'none',
                          letterSpacing: 'normal',
                          fontSize: '12px',
                        }}
                      >
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
