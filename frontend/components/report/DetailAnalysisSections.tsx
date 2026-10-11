import { Outfit } from 'next/font/google';

import type { ReactNode } from 'react';
import { UsersRound, Store, TrendingUp, type LucideIcon } from 'lucide-react';
import FloatingPopulationSection from '@/components/report/FloatingPopulationSection';
import CompetitorAnalysisSection from '@/components/report/CompetitorAnalysisSection';
import OpenCloseTrendSection from '@/components/report/OpenCloseTrendSection';
import { colors } from '@/styles/tokens';
import type {
  BusinessLifecycleData,
  CommercialAreaData,
  FloatingPopulationData,
} from '@/lib/mockData/report';
import type { IndustryAssessment } from '@/lib/api/types';

const outfit = Outfit({ subsets: ['latin'], weight: ['600', '700'] });

/**
 * 오케스트레이터에 아직 안 붙은 에이전트(source_analyses에서 agent_id를
 * 못 찾은 경우)일 때 구역 내용 대신 보여주는 안내문. 페이지 전체가 깨지지
 * 않도록 해당 구역만 이 문구로 대체한다.
 */
function UnavailableNote({ message }: { message: string }) {
  return (
    <div className="flex w-full items-center justify-center px-8 py-16">
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

type SectionProps<T> = {
  data?: T;
  unavailable?: boolean;
  period?: string;
};

/**
 * 경쟁업체 구역은 상권 데이터(data) 외에 추천·비추천 업종 목록도 필요하다
 * — "업종별 경쟁 지표" 카드가 그 업종들을 기준으로 그려지기 때문.
 * 나머지 두 구역과 같은 { data, unavailable } 구조를 유지하면서 두 필드만
 * 덧붙인다.
 */
type CompetitorSectionProps = SectionProps<CommercialAreaData> & {
  recommendations?: IndustryAssessment[];
  notRecommended?: IndustryAssessment[];
};

// FloatingPopulationSection, CompetitorAnalysisSection, OpenCloseTrendSection
// 모두 자체적으로 좌우/상하 여백을 갖고 있어 별도 래퍼 없이 그대로 배치한다.
export default function DetailAnalysisSections({
  floatingPopulation,
  competitor,
  openClose,
}: {
  floatingPopulation?: SectionProps<FloatingPopulationData>;
  competitor?: CompetitorSectionProps;
  openClose?: SectionProps<BusinessLifecycleData>;
}) {
  const sections: {
    id: string;
    label: string;
    title: string;
    description: string;
    accent: string;
    tint: string;
    icon: LucideIcon;
    content: ReactNode;
  }[] = [
    {
      id: 'foot-traffic',
      label: '유동인구',
      title: '주변에 어떤 사람들이 오나요?',
      description: '사람들의 규모와 방문 시간대를 살펴봅니다.',
      accent: '#006B65',
      tint: '#EAF5F3',
      icon: UsersRound,
      content: floatingPopulation?.unavailable ? (
        <UnavailableNote message="유동인구 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <FloatingPopulationSection
          data={floatingPopulation?.data}
          compactReference
        />
      ),
    },
    {
      id: 'competitors',
      label: '경쟁업체',
      title: '주변에 비슷한 가게가 얼마나 있나요?',
      description:
        '같은 업종의 분포를 살펴봅니다. 경쟁점이 적어도 수요가 적을 수 있으므로 유동인구와 함께 판단하세요.',
      accent: '#315F9A',
      tint: '#EDF2F9',
      icon: Store,
      content: competitor?.unavailable ? (
        <UnavailableNote message="경쟁업체 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <CompetitorAnalysisSection
          data={competitor?.data}
          recommendations={competitor?.recommendations}
          notRecommended={competitor?.notRecommended}
        />
      ),
    },
    {
      id: 'open-close',
      label: '개폐업 추이',
      title: '어떤 업종이 늘고 줄고 있나요?',
      description:
        '새로 생기고 문을 닫는 가게의 흐름을 살펴봅니다. 비율과 건수, 관측 기간을 함께 확인하세요.',
      accent: '#705493',
      tint: '#F3EEF7',
      icon: TrendingUp,
      content: openClose?.unavailable ? (
        <UnavailableNote message="개폐업 분석 데이터를 아직 받아오지 못했습니다." />
      ) : (
        <OpenCloseTrendSection data={openClose?.data} />
      ),
    },
  ];

  return (
    <div className="flex w-full flex-col items-start pt-8">
      <div
        id="detail-analysis"
        className="flex w-full scroll-mt-4 flex-col items-start px-8"
      >
        <h2
          className={`${outfit.className} text-25 font-bold`}
          style={{ color: colors.neutral.black }}
        >
          상세 분석
        </h2>
        <p className="pt-1 text-sm text-gray-500">
          유동인구, 경쟁 밀도, 업종 생존율 데이터를 기반으로 추천 결과의 근거를
          확인하세요.
        </p>
      </div>

      <div className="mt-6 w-full">
        {sections.map(
          (
            {
              id,
              label,
              title,
              description,
              accent,
              tint,
              icon: Icon,
              content,
            },
            index
          ) => (
            <section
              key={id}
              id={id}
              aria-labelledby={`${id}-heading`}
              className="w-full scroll-mt-24 pb-14"
            >
              <header
                className="mx-8 mb-2 flex items-center gap-6 rounded-2xl border-l-4 px-8 py-8"
                style={{ backgroundColor: tint, borderColor: accent }}
              >
                <span
                  className="text-5xl font-bold tracking-tight"
                  style={{ color: accent }}
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div>
                  <div
                    className="mb-3 flex items-center gap-2 text-base font-semibold"
                    style={{ color: accent }}
                  >
                    <Icon size={22} aria-hidden="true" />
                    {label}
                  </div>
                  <h3
                    id={`${id}-heading`}
                    className="text-[28px] leading-snug font-bold text-gray-900"
                  >
                    {title}
                  </h3>
                  <p className="mt-2 text-lg leading-7 text-gray-600">
                    {description}
                  </p>
                </div>
              </header>
              <p className="mx-8 mt-4 text-sm leading-6 text-gray-600">
                관측 기간 ·{' '}
                {(id === 'foot-traffic'
                  ? floatingPopulation?.period
                  : id === 'competitors'
                    ? competitor?.period
                    : openClose?.period) ||
                  '자료별 출처·기간을 확인하세요. 단일 관측 기간은 제공되지 않았습니다.'}
              </p>
              {content}
            </section>
          )
        )}
      </div>
    </div>
  );
}
