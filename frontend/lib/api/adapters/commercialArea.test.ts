import { describe, expect, it } from 'vitest';
import { adaptCommercialArea } from '@/lib/api/adapters/commercialArea';

// backend/app/agents/commercial_area/schemas.py의 CommercialAreaData.model_dump()
// 형태(snake_case)를 그대로 흉내낸 샘플. 실제 필드 이름을 그대로 써서,
// 어댑터가 스키마가 바뀌면 눈에 보이게 깨지도록 한다.
const rawSample: Record<string, unknown> = {
  description: '테스트 상권 설명',
  radius_m: 500,
  store_total: 120,
  data_reference_date: '2026년 1월 조회',
  by_major: [
    {
      code: 'I',
      name: '음식점업',
      count: 50,
      share: 0.4,
      density_per_km2: 12.3,
    },
  ],
  by_middle: [
    {
      code: 'I201',
      name: '한식 음식점업',
      major_code: 'I',
      major_name: '음식점업',
      count: 30,
      share: 0.25,
      density_per_km2: 7.1,
      density_sq: 0.5,
      lq: 1.24,
      lq_district: null,
      same_type_count: 30,
      diff_type_count: 90,
      marshallian: 0.1,
      jacobian: 0.2,
      major_cluster_count: 5,
      major_cluster_diversity: 0.6,
    },
  ],
  by_radius: [
    {
      radius_m: 500,
      store_total: 120,
      category_count: 20,
      absent_category_count: 3,
      top_by_count: [
        {
          rank: 1,
          code: 'I201',
          name: '한식 음식점업',
          count: 30,
          density_per_km2: 7.1,
          note: '가장 많음',
        },
      ],
      bottom_by_count: [],
      top_by_concentration: [],
      top_by_specialization: [],
      explanations: {
        store_total: 'x',
        top: 'x',
        bottom: 'x',
        concentration: 'x',
        specialization: 'x',
      },
    },
  ],
  diversity: { hhi_major: 0.1, hhi_middle: 0.2, effective_categories: 8.5 },
  restaurant_density: {
    value: 10,
    squared: 100,
    unit: 'stores_per_km2',
    store_count: 30,
    seoul_percentile: 60,
  },
  franchise: {
    count: 12,
    ratio: 0.1,
    independent_count: 108,
    independent_ratio: 0.9,
    by_middle: [],
    method: 'brand_name_match',
    confidence: 'medium',
    base_year: 2025,
  },
  lq_baseline: {
    requested_radius_m: 1000,
    applied_radius_m: 800,
    store_total: 300,
  },
  district_baseline: {
    signgu_code: '11680',
    signgu_name: '강남구',
    store_total: 5000,
  },
  district_specialization: [
    {
      rank: 1,
      code: 'I212',
      name: '커피·음료업',
      count: 40,
      times_vs_surroundings: 2.1,
      note: '주변보다 2.1배 많음',
    },
  ],
  trade_areas: [],
  summary: null,
  summary_text: null,
  sources: [],
};

describe('adaptCommercialArea', () => {
  it('snake_case 원본을 camelCase CommercialAreaData로 옮긴다', () => {
    const result = adaptCommercialArea(rawSample, {
      status: 'ok',
      warnings: [],
    });

    expect(result.status).toBe('ok');
    expect(result.radiusM).toBe(500);
    expect(result.storeTotal).toBe(120);
    expect(result.dataReferenceDate).toBe('2026년 1월 조회');

    expect(result.byMajor).toEqual([
      {
        code: 'I',
        name: '음식점업',
        count: 50,
        share: 0.4,
        densityPerKm2: 12.3,
      },
    ]);

    expect(result.byRadius).toEqual([
      {
        radiusM: 500,
        storeTotal: 120,
        categoryCount: 20,
        absentCategoryCount: 3,
        topByCount: [
          {
            rank: 1,
            code: 'I201',
            name: '한식 음식점업',
            count: 30,
            densityPerKm2: 7.1,
            note: '가장 많음',
          },
        ],
      },
    ]);

    expect(result.diversity).toEqual({ effectiveCategories: 8.5 });
    expect(result.franchise).toEqual({
      count: 12,
      ratio: 0.1,
      confidence: 'medium',
    });
    expect(result.lqBaseline).toEqual({
      requestedRadiusM: 1000,
      appliedRadiusM: 800,
    });
    expect(result.districtBaseline).toEqual({ signguName: '강남구' });
    expect(result.districtSpecialization).toEqual([
      {
        rank: 1,
        code: 'I212',
        name: '커피·음료업',
        count: 40,
        timesVsSurroundings: 2.1,
        note: '주변보다 2.1배 많음',
      },
    ]);

    // by_middle 전체가 그대로 옮겨진다(추천 10개로 미리 걸러내지 않음 —
    // 파일 상단 mapMiddleCategory 주석 참고).
    expect(result.byMiddleForRecommendations).toEqual([
      {
        code: 'I201',
        name: '한식 음식점업',
        sameTypeCount: 30,
        diffTypeCount: 90,
        lq: 1.24,
        lqDistrict: null,
      },
    ]);
  });

  it('franchise/district_baseline이 없으면 null로 채운다', () => {
    const result = adaptCommercialArea({
      ...rawSample,
      franchise: null,
      district_baseline: null,
    });

    expect(result.franchise).toBeNull();
    expect(result.districtBaseline).toBeNull();
  });

  it('district_baseline에 signgu_name이 없으면 null로 취급한다', () => {
    const result = adaptCommercialArea({
      ...rawSample,
      district_baseline: {
        signgu_code: '11680',
        signgu_name: null,
        store_total: 5000,
      },
    });

    expect(result.districtBaseline).toBeNull();
  });

  it('data_reference_date가 없으면 빈 문자열로 채운다', () => {
    const result = adaptCommercialArea({
      ...rawSample,
      data_reference_date: null,
    });

    expect(result.dataReferenceDate).toBe('');
  });

  it('envelope을 안 넘기면 status ok/warnings 빈 배열로 기본 처리한다', () => {
    const result = adaptCommercialArea(rawSample);

    expect(result.status).toBe('ok');
    expect(result.warnings).toEqual([]);
  });

  it('빈 객체(no_data/error 상태의 data={})를 넣어도 안전한 기본값으로 채운다', () => {
    const result = adaptCommercialArea(
      {},
      { status: 'no_data', warnings: ['자료 없음'] }
    );

    expect(result.status).toBe('no_data');
    expect(result.warnings).toEqual(['자료 없음']);
    expect(result.byMajor).toEqual([]);
    expect(result.byRadius).toEqual([]);
    expect(result.byMiddleForRecommendations).toEqual([]);
    expect(result.franchise).toBeNull();
    expect(result.districtBaseline).toBeNull();
  });
});
