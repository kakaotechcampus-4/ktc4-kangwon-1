import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import WithdrawnNotice from '@/components/landing/WithdrawnNotice';

afterEach(() => {
  window.history.replaceState({}, '', '/');
});

describe('탈퇴 알림', () => {
  it('탈퇴하고 첫 화면에 오면 탈퇴했다고 알린다', async () => {
    window.history.replaceState({}, '', '/?withdrawn=1');
    render(<WithdrawnNotice />);
    expect(
      await screen.findByText('탈퇴했어요. 계정과 로그인 정보를 지웠어요.')
    ).toBeTruthy();
  });

  it('알림을 띄운 뒤 주소에서 탈퇴 표시를 지워 새로고침·공유 때 다시 뜨지 않게 한다', async () => {
    window.history.replaceState({}, '', '/?withdrawn=1');
    render(<WithdrawnNotice />);
    expect(
      await screen.findByText('탈퇴했어요. 계정과 로그인 정보를 지웠어요.')
    ).toBeTruthy();
    expect(window.location.search).toBe('');
  });

  it('닫으면 알림이 사라진다', async () => {
    window.history.replaceState({}, '', '/?withdrawn=1');
    render(<WithdrawnNotice />);
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: '알림 닫기' }));
    expect(
      screen.queryByText('탈퇴했어요. 계정과 로그인 정보를 지웠어요.')
    ).toBeNull();
  });

  it('그냥 첫 화면에 오면 아무것도 띄우지 않는다', () => {
    render(<WithdrawnNotice />);
    expect(
      screen.queryByText('탈퇴했어요. 계정과 로그인 정보를 지웠어요.')
    ).toBeNull();
  });
});
