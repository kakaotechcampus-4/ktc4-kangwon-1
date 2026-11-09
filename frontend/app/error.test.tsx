import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ErrorPage from '@/app/error';

vi.mock('@/components/layout/Header', () => ({ default: () => null }));

describe('화면 오류', () => {
  it('한국어 안내를 보여 주고 다시 시도를 누르면 Next가 준 retry를 부른다', async () => {
    const retry = vi.fn();
    render(<ErrorPage retry={retry} />);

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: '화면을 여는 중에 문제가 생겼어요',
      })
    ).toBeTruthy();
    expect(screen.getByText('SOMETHING WENT WRONG')).toBeTruthy();
    expect(screen.getByText('잠시 후 다시 시도해 주세요.')).toBeTruthy();
    expect(screen.getByText('다시 시도해 주세요')).toBeTruthy();
    expect(
      screen.getByText('같은 문제가 계속되면 홈에서 다시 시작해 주세요.')
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
