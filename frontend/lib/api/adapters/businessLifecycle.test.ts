import { beforeEach, describe, expect, it, vi } from 'vitest';
import { adaptBusinessLifecycle } from '@/lib/api/adapters/businessLifecycle';

// feature/mvp1-refact의 input_builder.py build_agent_input() →
// formatter.py format_for_mediator()가 실제로 만드는 AgentAnalysis.data
// 형태(snake_case, industries[] + metrics 중첩)를 그대로 흉내낸 샘플.
// 실제 필드 이름을 그대로 써서, 스키마가 바뀌면 눈에 보이게 깨지도록 한다.
function buildRawSample(): Record<string, unknown> {
  return {
    summary: '테스트 요약 문장입니다.',
    metadata: { area_code: '3120240', base_quarter: '2026Q3' },
    coverage: {
      target_industries: 75,
      scored_industries: 56,
      unscored_industries: 19,
    },
    taxonomy: { id: 'sbiz-middle-75', version: 'abc123' },
    scoring_method: {
      description:
        '테스트 상권 개폐업 데이터를 기반으로 계산한 Lifecycle Score',
      score_type: 'relative',
      weights: {
        recent_year_close_rate: 0.35,
        net_change_rate: 0.25,
        turnover_stability: 0.2,
        close_rate_trend: 0.2,
      },
      notes: ['lifecycle_score는 미래 생존확률이 아니다.'],
    },
    industries: [
      {
        industry_id: 'I201',
        industry_name: '한식음식점',
        score: 35.1,
        type: '성장·안정형',
        confidence: 'high',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 55,
          avg_store_count: 52.3,
          period_open_count: 20,
          period_close_count: 14,
          period_net_change: 6,
          avg_open_rate: 12.7,
          avg_close_rate: 8.9,
          net_change_rate: 3.8,
          turnover_rate: 21.6,
          recent_year_open_count: 6,
          recent_year_close_count: 4,
          recent_year_net_change: 2,
          recent_year_close_rate: 7.27,
          recent_year_net_change_rate: 3.64,
          oldest_year_close_rate: 10.5,
          close_rate_trend: -3.23,
        },
        evidence: [
          '최근 3년 동안 개업 20건, 폐업 14건으로 순증감은 +6건입니다.',
        ],
        warning: null,
      },
      {
        industry_id: 'X999',
        industry_name: '기타 외국식 음식점',
        score: null,
        type: '판단 보류',
        confidence: 'none',
        data_available: false,
        score_available: false,
        data_status: 'unsupported',
        data_complete: false,
        metrics: {
          latest_store_count: null,
          avg_store_count: null,
          period_open_count: null,
          period_close_count: null,
          period_net_change: null,
          avg_open_rate: null,
          avg_close_rate: null,
          recent_year_close_rate: null,
          net_change_rate: null,
          turnover_rate: null,
          close_rate_trend: null,
        },
        source_coverage: {
          expected_source_count: 0,
          observed_source_rows: 0,
          expected_source_rows: 0,
          observed_quarters: 0,
        },
        evidence: [],
        warning: '서울시 생활밀접업종 데이터에 직접 대응 업종 없음',
      },
      {
        industry_id: 'I212',
        industry_name: '카페·음료점',
        score: 4.5,
        type: '쇠퇴·위험형',
        confidence: 'medium',
        data_available: true,
        score_available: true,
        data_status: 'observed',
        data_complete: true,
        metrics: {
          observed_quarters: 12,
          latest_store_count: 17,
          avg_store_count: 16.1,
          period_open_count: 8,
          period_close_count: 12,
          period_net_change: -4,
          avg_open_rate: 16.6,
          avg_close_rate: 24.9,
          net_change_rate: -8.3,
          turnover_rate: 41.5,
          recent_year_open_count: 2,
          recent_year_close_count: 3,
          recent_year_net_change: -1,
          recent_year_close_rate: 17.65,
          recent_year_net_change_rate: -5.88,
          oldest_year_close_rate: 10.0,
          close_rate_trend: 7.65,
        },
        evidence: [
          '최근 3년 동안 개업 8건, 폐업 12건으로 순증감은 -4건입니다.',
        ],
        warning: null,
      },
    ],
  };
}

describe('adaptBusinessLifecycle', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('coverage/scoring_method를 필터링 없이 그대로 옮긴다', () => {
    const result = adaptBusinessLifecycle(
      buildRawSample(),
      ['한식음식점'],
      ['카페·음료점']
    );

    expect(result).not.toBeNull();
    expect(result?.coverage).toEqual({
      target_industries: 75,
      scored_industries: 56,
      unscored_industries: 19,
    });
    expect(result?.scoring_method.weights).toEqual({
      recent_year_close_rate: 0.35,
      net_change_rate: 0.25,
      turnover_stability: 0.2,
      close_rate_trend: 0.2,
    });
    expect(result?.summary).toBe('테스트 요약 문장입니다.');
  });

  it('recommendedNames/notRecommendedNames와 이름이 일치하는 업종만 남긴다', () => {
    const result = adaptBusinessLifecycle(
      buildRawSample(),
      ['한식음식점'],
      ['카페·음료점']
    );

    expect(result?.industries).toHaveLength(2);
    expect(result?.industries.map((item) => item.industry_name)).toEqual([
      '한식음식점',
      '카페·음료점',
    ]);
    expect(
      result?.industries.some(
        (item) => item.industry_name === '기타 외국식 음식점'
      )
    ).toBe(false);
  });

  it('industry_id를 문자열로 그대로 옮긴다(숫자로 바꾸지 않음)', () => {
    const result = adaptBusinessLifecycle(buildRawSample(), ['한식음식점'], []);

    expect(result?.industries[0].industry_id).toBe('I201');
    expect(typeof result?.industries[0].industry_id).toBe('string');
  });

  it('score가 null인 판단 보류 업종도 그대로 옮기고, source_coverage를 포함한다', () => {
    const result = adaptBusinessLifecycle(
      buildRawSample(),
      [],
      ['기타 외국식 음식점']
    );

    const unscored = result?.industries.find(
      (item) => item.industry_name === '기타 외국식 음식점'
    );
    expect(unscored?.score).toBeNull();
    expect(unscored?.confidence).toBe('none');
    expect(unscored?.data_available).toBe(false);
    expect(unscored?.source_coverage).toEqual({
      expected_source_count: 0,
      observed_source_rows: 0,
      expected_source_rows: 0,
      observed_quarters: 0,
    });
    // 판단 보류 업종의 metrics는 17개 키 중 11개만 온다 — 없는 키는
    // undefined여야 하고(0으로 채워지면 안 됨), 있는 키는 null이어야 한다.
    expect(unscored?.metrics.observed_quarters).toBeUndefined();
    expect(unscored?.metrics.avg_close_rate).toBeNull();
  });

  it('score가 있는 업종은 source_coverage가 없다(undefined)', () => {
    const result = adaptBusinessLifecycle(buildRawSample(), ['한식음식점'], []);

    expect(result?.industries[0].source_coverage).toBeUndefined();
  });

  it('이름 매칭에 실패한 업종이 있으면 콘솔에 한 번만(모아서) 경고한다', () => {
    const warnSpy = vi.spyOn(console, 'warn');
    adaptBusinessLifecycle(buildRawSample(), ['무인점포'], ['프랜차이즈 없음']);

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0][0]).toContain('무인점포');
    expect(warnSpy.mock.calls[0][0]).toContain('프랜차이즈 없음');
  });

  it('일치하는 이름이 하나도 없으면 industries가 빈 배열이다', () => {
    const result = adaptBusinessLifecycle(
      buildRawSample(),
      ['무인점포'],
      ['프랜차이즈 없음']
    );

    expect(result?.industries).toEqual([]);
  });

  it('빈 객체({})를 받으면 null을 반환한다', () => {
    const result = adaptBusinessLifecycle({}, ['한식음식점'], ['카페·음료점']);

    expect(result).toBeNull();
  });

  it('industries 키 자체가 없는 형태(옛 mock 스텁 등)를 받으면 null을 반환한다', () => {
    const result = adaptBusinessLifecycle(
      { description: '목업 개폐업 자료입니다.', industry_scores: [] },
      ['한식음식점'],
      ['카페·음료점']
    );

    expect(result).toBeNull();
  });

  it('industries 키는 있지만 항목 모양이 다르고 coverage/scoring_method가 없으면 null을 반환한다', () => {
    // backend/app/mocks.py의 옛 목업 스텁을 그대로 흉내낸 것 — industries가
    // 배열인 건 우연히 같지만 항목이 {middle, open_count, close_count}라
    // industry_id/industry_name조차 없다. industries가 배열이라는 것만
    // 확인하면 이 스텁을 걸러내지 못하고 "매칭된 업종이 없습니다"라는
    // 엉뚱한 빈 결과를 돌려주게 된다(실제로 한 번 이렇게 되는 걸 확인했다) —
    // coverage/scoring_method도 같이 확인해야 한다.
    const result = adaptBusinessLifecycle(
      {
        description: '목업 개폐업 자료입니다.',
        industries: [{ middle: '한식음식점', open_count: 12, close_count: 9 }],
      },
      ['한식음식점'],
      ['카페·음료점']
    );

    expect(result).toBeNull();
  });

  it('coverage/scoring_method 내부 필드가 비어 있으면 안전한 기본값으로 채운다', () => {
    // coverage/scoring_method 키 자체는 있어야 한다(가드 조건) — 그
    // 안쪽 필드가 비어 있는 경우를 테스트한다.
    const result = adaptBusinessLifecycle(
      { industries: [], coverage: {}, scoring_method: {} },
      ['한식음식점'],
      ['카페·음료점']
    );

    expect(result).not.toBeNull();
    expect(result?.coverage).toEqual({
      target_industries: 0,
      scored_industries: 0,
      unscored_industries: 0,
    });
    expect(result?.scoring_method).toEqual({
      description: '',
      score_type: '',
      weights: {
        recent_year_close_rate: 0,
        net_change_rate: 0,
        turnover_stability: 0,
        close_rate_trend: 0,
      },
      notes: [],
    });
    expect(result?.industries).toEqual([]);
    expect(result?.summary).toBeUndefined();
  });
});
