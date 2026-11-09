import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import GlobalErrorPage from '@/app/global-error';

describe('전체 화면 오류', () => {
  it('전역 CSS 없이 한국어 안내를 그리고 다시 시도를 누르면 retry를 부른다', async () => {
    const retry = vi.fn();
    render(<GlobalErrorPage retry={retry} />);

    expect(document.documentElement.lang).toBe('ko');
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: '화면을 여는 중에 문제가 생겼어요',
      })
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: '홈으로' }).getAttribute('href')
    ).toBe('/');

    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '다시 시도' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
