import { UsersRound, CircleCheck, CircleAlert } from 'lucide-react';
import { colors } from '@/styles/tokens';

type Props = {
  variant?: 'summary' | 'reasons';
  summary?: string;
  recommendedReasons?: string[];
  recommendedCategoryName?: string;
  notRecommendedReasons?: string[];
  notRecommendedCategoryName?: string;
};

export default function AIAnalysisSummary({
  variant = 'summary',
  summary,
  recommendedReasons,
  recommendedCategoryName,
  notRecommendedReasons,
  notRecommendedCategoryName,
}: Props = {}) {
  const isReal =
    summary !== undefined ||
    recommendedReasons !== undefined ||
    notRecommendedReasons !== undefined;
  const recommendedName =
    recommendedCategoryName ?? (isReal ? '추천 업종' : '네일·뷰티');
  const notRecommendedName =
    notRecommendedCategoryName ?? (isReal ? '비추천 업종' : '헬스장');
  const recommendedLead = isReal
    ? (recommendedReasons?.[0] ?? '추천 이유가 제공되지 않았습니다.')
    : '동종 점포가 적어 우선 검토할 만해요.';
  const cautionLead = isReal
    ? (notRecommendedReasons?.[0] ?? '비추천 이유가 제공되지 않았습니다.')
    : '개폐업 흐름과 시설 조건을 함께 살펴봐야 해요.';

  return (
    <section
      className={variant === 'reasons' ? 'w-full pt-5' : 'w-full px-8 pt-8'}
      aria-label={
        variant === 'summary' ? 'AI 분석 요약' : '업종 추천과 주의 이유'
      }
    >
      <div
        className={
          variant === 'summary'
            ? 'overflow-hidden rounded-2xl border border-gray-200 bg-white'
            : ''
        }
      >
        {variant === 'summary' && (
          <>
            <header
              className="flex items-center justify-between px-8 py-5"
              style={{ backgroundColor: colors.brand.dark }}
            >
              <h2
                id="ai-summary-title"
                className="text-2xl font-bold text-white"
              >
                AI 분석 요약
              </h2>
              {!isReal && (
                <span className="text-sm text-white/80">예시 데이터 기준</span>
              )}
            </header>
            <div className="px-8 py-7">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-gray-600">
                <UsersRound size={22} aria-hidden="true" />내 공실 주변은 이런
                상권이에요
              </h3>
              {isReal ? (
                <p className="mt-4 max-w-[80ch] whitespace-pre-line text-xl leading-8 font-semibold text-gray-900">
                  {summary ||
                    '종합 설명이 제공되지 않았습니다. 상세 분석에서 확보된 자료를 확인해 주세요.'}
                </p>
              ) : (
                <>
                  <p className="mt-4 text-2xl leading-9 font-bold text-gray-900">
                    40·50대가 유동인구의{' '}
                    <strong className="text-[#006B65]">46%</strong>를 차지해요.
                  </p>
                  <p className="mt-3 max-w-[80ch] text-lg leading-8 text-gray-700">
                    반경 500m 내 한식 음식점은 <strong>31개</strong>,
                    이용·미용업은 <strong>34개</strong>로 집계됐어요.
                    <br />
                    비슷한 업종을 고려한다면 주변 점포와의 차별화가 중요합니다.
                  </p>
                </>
              )}
            </div>
          </>
        )}
        {variant === 'reasons' && (
          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-2xl border border-[#C7E4DD] border-t-4 border-t-[#00A895] bg-gradient-to-br from-[#E5F4EE] to-white px-6 py-6">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-[#006B65]">
                <span className="flex size-9 items-center justify-center rounded-xl bg-[#006B65] text-white">
                  <CircleCheck size={22} aria-hidden="true" />
                </span>
                {recommendedName} 추천 이유
              </h3>
              <p className="mt-4 text-[22px] leading-8 font-bold text-gray-900">
                {recommendedLead}
              </p>
              <p className="mt-3 text-lg leading-8 text-gray-700">
                {isReal ? (
                  recommendedReasons?.slice(1, 2).join(' ')
                ) : (
                  <>
                    반경 500m 내 동종 점포는{' '}
                    <strong className="text-[#006B65]">1개</strong>예요.
                    <br />
                    실제 입점 전에는 접근성과 급·배수 조건을 확인해야 합니다.
                  </>
                )}
              </p>
            </div>
            <div className="rounded-2xl border border-[#F0D8CE] border-t-4 border-t-[#C65A37] bg-gradient-to-br from-[#FFF0E8] to-white px-6 py-6">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-[#A34828]">
                <span className="flex size-9 items-center justify-center rounded-xl bg-[#A34828] text-white">
                  <CircleAlert size={22} aria-hidden="true" />
                </span>
                {notRecommendedName} 검토 시 주의할 점
              </h3>
              <p className="mt-4 text-[22px] leading-8 font-bold text-gray-900">
                {cautionLead}
              </p>
              <p className="mt-3 text-lg leading-8 text-gray-700">
                {isReal ? (
                  notRecommendedReasons?.slice(1, 2).join(' ')
                ) : (
                  <>
                    자료상 폐업률은{' '}
                    <strong className="text-[#A34828]">47.2%</strong>예요.
                    <br />
                    층고·하중·소음 조건은 아직 확인되지 않아 추가 검토가
                    필요합니다.
                  </>
                )}
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
