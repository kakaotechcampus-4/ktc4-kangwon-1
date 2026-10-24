import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import FacilityRows from './FacilityRows';

function render(
  facilities: Parameters<typeof FacilityRows>[0]['facilities']
): string {
  return renderToStaticMarkup(
    createElement(FacilityRows, { facilities, onChange: () => {} })
  );
}

describe('확인 화면 시설 세 칸', () => {
  it('배기·주방·급배수를 네 가지 선택지와 함께 그린다', () => {
    const html = render({
      ventilation: 'unknown',
      kitchen: 'unknown',
      water_supply: 'unknown',
    });
    const order = ['배기(덕트)', '주방', '급배수'].map((label) =>
      html.indexOf(`>${label}<`)
    );
    expect(order.every((index) => index >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    for (const option of ['있음', '설치 가능', '불가', '모름']) {
      expect(html.split(`>${option}<`).length - 1).toBe(3);
    }
  });

  it('모름이면 출처 표시가 없고 고른 칸에만 직접 입력이 붙는다', () => {
    expect(
      render({
        ventilation: 'unknown',
        kitchen: 'unknown',
        water_supply: 'unknown',
      })
    ).not.toContain('직접 입력');
    const chosen = render({
      ventilation: 'unavailable',
      kitchen: 'unknown',
      water_supply: 'unknown',
    });
    expect(chosen.split('직접 입력').length - 1).toBe(1);
  });
});
