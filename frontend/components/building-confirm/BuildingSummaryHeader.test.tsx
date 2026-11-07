import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import BuildingSummaryHeader from './BuildingSummaryHeader';
import { emptyBuildingInfo } from '@/lib/api/buildingRegistry';

vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));

const INPUT = '서울 송파구 위례광장로 199';

describe('상가 정보 확인 머리말', () => {
  it('건축물대장이 찾은 건물 이름과 주소를 입력 주소 아래에 보여 준다', () => {
    const building = {
      ...emptyBuildingInfo('서울특별시 송파구 위례광장로 199', '1층', ''),
      buildingName: '위례 중앙타워',
    };
    render(<BuildingSummaryHeader building={building} address={INPUT} />);
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(INPUT);
    expect(
      screen.getByText(
        '건축물대장: 위례 중앙타워 · 서울특별시 송파구 위례광장로 199'
      )
    ).toBeTruthy();
  });

  it('이름이 없으면 대장 주소만 보여 준다', () => {
    const building = emptyBuildingInfo(
      '서울특별시 송파구 위례광장로 199',
      '1층',
      ''
    );
    render(<BuildingSummaryHeader building={building} address={INPUT} />);
    expect(
      screen.getByText('건축물대장: 서울특별시 송파구 위례광장로 199')
    ).toBeTruthy();
  });

  it('이름이 없고 주소가 입력과 같으면 줄을 만들지 않는다', () => {
    const building = emptyBuildingInfo(INPUT, '1층', '');
    render(<BuildingSummaryHeader building={building} address={INPUT} />);
    expect(screen.queryByText(/건축물대장:/)).toBeNull();
  });
});
