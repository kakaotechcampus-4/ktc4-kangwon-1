import { describe, expect, it } from 'vitest';
import { rankingView } from './industryRanking';
import { indexFacts } from '@/lib/api/segments';
import type { DecisionResult, FinalCandidate } from '@/lib/api/types';

function candidate(
  code: string,
  name: string,
  reason: string,
  risk = ''
): FinalCandidate {
  return {
    industry_code: code,
    industry_name: name,
    code_points: 62,
    L_points: 6,
    L_status: 'observed',
    A: 90,
    B: 60,
    H: 80,
    lower_ratio: 0.67,
    upper_ratio: 0.89,
    coverage: 0.8,
    demand_coverage: 0.8,
    competition_coverage: 0.8,
    G: '해당 없음',
    badge: '추천',
    confirmation_conditions: [],
    reasons_segments: reason ? [{ type: 'text', text: reason }] : [],
    risks_segments: risk ? [{ type: 'text', text: risk }] : [],
    confirmation_conditions_segments: [],
    fact_ids: [],
    review_state: 'reviewed',
  };
}

const top5 = [
  candidate(
    'M103',
    '법무 서비스',
    '주변 사무실이 많습니다.',
    '임대료를 확인하세요.'
  ),
  candidate('M104', '회계·세무 서비스', '법인 수요가 있습니다.'),
  candidate('M105', '회사 본부·경영 컨설팅 서비스', '업무 지구입니다.'),
  candidate('N102', '건물 청소·방제', '관리 건물이 많습니다.'),
  candidate('N105', '여행 서비스', '온라인 예약 비중이 큽니다.'),
];

const base = {
  summary_segments: [],
  top5,
  excluded_candidates: [
    candidate('N105', '여행 서비스', '온라인 예약 비중이 큽니다.'),
  ],
  condition_excluded: [
    {
      industry_code: 'I201',
      industry_name: '한식 음식점',
      reasons: ['배기(덕트) 설치 불가'],
      score_rank: 2,
    },
  ],
  regulation_excluded: [
    { industry_code: 'I101', industry_name: '일반·생활 숙박' },
  ],
  ranking: [
    ...top5.map((c, i) => ({
      industry_code: c.industry_code,
      industry_name: c.industry_name,
      rank: i + 1,
      ai_excluded: c.industry_code === 'N105',
    })),
    {
      industry_code: 'G204',
      industry_name: '종합 소매',
      rank: 6,
      ai_excluded: false,
    },
  ],
} as unknown as DecisionResult;

describe('업종 비교 순위', () => {
  it('서버 순위대로 보여 주고 1~5위에만 이유와 확인을 붙인다', () => {
    const view = rankingView(base, indexFacts([]));
    expect(view.items.map((item) => [item.rank, item.name])).toEqual([
      [1, '법무 서비스'],
      [2, '회계·세무 서비스'],
      [3, '회사 본부·경영 컨설팅 서비스'],
      [4, '건물 청소·방제'],
      [5, '여행 서비스'],
      [6, '종합 소매'],
    ]);
    expect(view.items[0]).toMatchObject({
      reasons: '주변 사무실이 많습니다.',
      checks: ['임대료를 확인하세요.'],
    });
    expect(view.items[0].detailTitle).toBe('추천 이유 보기');
    expect(view.items[4]).toMatchObject({
      aiExcluded: true,
      detailTitle: 'AI가 뺀 이유 보기',
    });
    expect(view.items[5].reasons).toBeUndefined();
    expect(view.notice).toBeNull();
    expect(view.label).toBe('6개 순위 · 2개 제외');
  });

  it('한 업종의 이유와 확인에 같은 공간 비교 문구를 한 번만 쓴다', () => {
    const spaceFit = {
      fact_id: 'sf',
      source: 'code',
      metric: 'space_fit',
      value: { area: '일치', confidence: 'low', ventilation: '미확인' },
      unit: '',
      period: '',
      spatial_scope: {},
      industry_code: 'M103',
      status: 'observed',
      citable: true,
      calc_version: '',
      provenance_ref: '',
    };
    const cited = { type: 'fact', fact_id: 'sf', format: 'text' } as const;
    const first = {
      ...top5[0],
      reasons_segments: [{ type: 'text', text: '면적이 맞습니다.' }, cited],
      risks_segments: [{ type: 'text', text: '배기를 확인하세요.' }, cited],
      confirmation_conditions_segments: [
        { type: 'text', text: '설비를 확정하세요.' },
        cited,
      ],
    } as FinalCandidate;
    const view = rankingView(
      { ...base, top5: [first, ...top5.slice(1)] } as DecisionResult,
      indexFacts([spaceFit] as never)
    );
    expect(view.items[0].reasons).toBe(
      '면적이 맞습니다. 면적 일치 · 배기(덕트) 미확인 (비교 신뢰도 낮음)'
    );
    expect(view.items[0].checks).toEqual([
      '배기를 확인하세요. 면적 일치 · 배기(덕트) 미확인',
      '설비를 확정하세요. 면적 일치 · 배기(덕트) 미확인',
    ]);
  });

  it('제외 설명은 순위에 남는다고 단정하지 않는다', () => {
    const view = rankingView(base, indexFacts([]));
    const excluded = view.groups.find((group) => group.title === '제외한 업종');
    expect(excluded?.description).not.toContain('순위에는');
  });

  it('조건 제외·AI 제외·규제 제외를 순위 아래 따로 모은다', () => {
    const view = rankingView(base, indexFacts([]));
    expect(view.groups.map((group) => [group.title, group.lines])).toEqual([
      [
        '조건 때문에 뺀 업종',
        ['한식 음식점 — 배기(덕트) 설치가 안 돼서 추천에서 뺐어요'],
      ],
      ['제외한 업종', ['여행 서비스 — 온라인 예약 비중이 큽니다.']],
      ['규제로 안 되는 업종', ['일반·생활 숙박']],
    ]);
  });

  it('점수는 보여 주지 않는다', () => {
    const text = JSON.stringify(rankingView(base, indexFacts([])));
    expect(text).not.toMatch(/점수|\d+점/);
  });

  it('전체 순위가 없는 예전 분석은 추천 업종만 순서대로 보여 주고 알린다', () => {
    const old = {
      ...base,
      ranking: undefined,
      regulation_excluded: undefined,
    } as unknown as DecisionResult;
    const view = rankingView(old, indexFacts([]));
    expect(view.items.map((item) => item.rank)).toEqual([1, 2, 3, 4, 5]);
    expect(view.items[4].aiExcluded).toBe(true);
    expect(view.notice).toContain('전체 순위');
    expect(view.label).toBe('추천 5개');
  });
});
