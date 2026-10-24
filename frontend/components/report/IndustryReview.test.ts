import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import IndustryReview from './IndustryReview';

describe('검토 후보 업종 안내', () => {
  it('숨은 공간 조정이 있으니 점수 순서라고 쓰지 않는다', () => {
    const html = renderToStaticMarkup(
      createElement(IndustryReview, { top5: [], excluded: [] })
    );
    expect(html).toContain('추천 순서입니다. 배지와 확인 조건을 함께 보세요');
    expect(html).not.toContain('점수가 높은 순서');
  });
});
