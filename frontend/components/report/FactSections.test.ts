import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FactCompetitionSection } from './FactSections';
import type {
  FactCompetition,
  FactCompetitionRow,
} from '@/lib/api/adapters/facts';

function row(
  code: string,
  competitionIndex: number | null,
  densityKind: FactCompetitionRow['densityKind']
): FactCompetitionRow {
  return {
    code,
    name: code,
    storeCount: 5,
    densityPerKm2: 10,
    competitionIndex,
    lq: 1,
    densityKind,
  };
}

describe('검토 후보 업종의 경쟁 상황', () => {
  it('밀도 열을 중립 이름으로 쓰고 업종 유형별 해석을 붙인다', () => {
    const data: FactCompetition = {
      radiusM: 500,
      comparisonRadiusM: 2000,
      period: '2026년 2분기',
      storeTotal: 15,
      effectiveCategories: 3,
      byMajor: [],
      topByCount: [],
      selected: [
        row('G208', 2.1, '모임형'),
        row('G204', 1.8, '근처형'),
        row('L102', null, '무관'),
      ],
    };
    const html = renderToStaticMarkup(
      createElement(FactCompetitionSection, { data })
    );
    expect(html).toContain('서울 대비 밀도');
    expect(html).not.toContain('경쟁 부담');
    expect(html).not.toContain('높을수록 경쟁이 셉니다');
    expect(html).toContain('몰릴수록 유리');
    expect(html).toContain('낮을수록 유리');
    expect(html).toContain('밀도와 무관');
  });
});
