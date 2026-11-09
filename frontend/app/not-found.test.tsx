import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import NotFoundPage from '@/app/not-found';

vi.mock('@/components/layout/Header', () => ({ default: () => null }));

describe('없는 주소 화면', () => {
  it('로그인 상태를 묻지 않고 한국어 안내와 홈·내 분석 기록 링크를 보여 준다', () => {
    render(<NotFoundPage />);

    expect(
      screen.getByRole('heading', { level: 1, name: '찾는 페이지가 없어요' })
    ).toBeTruthy();
    expect(screen.getByText('PAGE NOT FOUND')).toBeTruthy();
    expect(
      screen.getByText('주소가 바뀌었거나 없어진 페이지예요.')
    ).toBeTruthy();
    expect(screen.getByText('이렇게 해 보세요')).toBeTruthy();
    expect(
      screen.getByText(
        '홈에서 공실 분석을 새로 시작하거나, 내 분석 기록에서 지난 리포트를 열어 보세요.'
      )
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: '홈으로' }).getAttribute('href')
    ).toBe('/');
    expect(
      screen.getByRole('link', { name: '내 분석 기록' }).getAttribute('href')
    ).toBe('/my/reports');
  });
});
