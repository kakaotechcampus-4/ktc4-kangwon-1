import { describe, expect, it } from 'vitest';
import { getKeyConclusionItems } from '@/components/report/KeyConclusion';

const checks = [
  '점수는 실제 임대 수요나 사업 지속성을 입증하지 않습니다. 필요한 공사 범위·허용·책임·견적과 관할기관 요건을 확인해야 합니다.',
  '임대료·공실 기간·공사비도 확인 대상입니다.',
];

describe('getKeyConclusionItems', () => {
  it('단어 속 "요"·"다"에서 자르지 않고 문장 끝에서만 나눈다', () => {
    const texts = getKeyConclusionItems(checks).flatMap((item) => [
      item.how,
      ...item.sources,
    ]);
    expect(texts).toContain(
      '점수는 실제 임대 수요나 사업 지속성을 입증하지 않습니다.'
    );
    for (const fragment of [
      '나 사업 지속성을 입증하지 않습니다.',
      '건을 확인해야 합니다.',
      '필요',
    ]) {
      expect(texts).not.toContain(fragment);
    }
  });

  it('주제에 안 맞는 문장은 "추가로 확인할 것" 한 칸에 모은다', () => {
    const others = getKeyConclusionItems(checks).filter(
      (item) => item.title === '추가로 확인할 것'
    );
    expect(others).toHaveLength(1);
    expect(others[0].how).toBe(
      '필요한 공사 범위·허용·책임·견적과 관할기관 요건을 확인해야 합니다. 임대료·공실 기간·공사비도 확인 대상입니다.'
    );
  });

  it('주제에 맞는 문장은 그 주제 칸으로 간다', () => {
    const customers = getKeyConclusionItems(checks).find(
      (item) => item.title === '이 업종을 찾을 손님'
    );
    expect(customers?.sources).toEqual([
      '점수는 실제 임대 수요나 사업 지속성을 입증하지 않습니다.',
    ]);
  });

  it('남는 문장이 없으면 "추가로 확인할 것" 칸을 만들지 않는다', () => {
    const items = getKeyConclusionItems(['전용면적을 실측하세요.']);
    expect(items.map((item) => item.title)).toEqual(['실제로 쓸 수 있는 면적']);
  });
});
