import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CTABanner from '@/components/landing/CTABanner';
import { saveVacancyInput } from '@/lib/api/resultStore';

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/lib/api/resultStore', () => ({ saveVacancyInput: vi.fn() }));

async function submit(address: string) {
  const user = userEvent.setup();
  render(<CTABanner />);
  await user.type(screen.getByLabelText('분석할 상가 주소'), address);
  await user.click(screen.getByRole('button', { name: /분석 시작/ }));
  return user;
}

describe('CTABanner 제출', () => {
  beforeEach(() => vi.clearAllMocks());

  it('보통 주소는 팝업 없이 바로 넘어간다', async () => {
    await submit('서울 강남구 테헤란로 152');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(saveVacancyInput).toHaveBeenCalledWith({
      roadAddress: '서울 강남구 테헤란로 152',
      floorUnit: '',
    });
    expect(router.push).toHaveBeenCalledWith('/building-confirm');
  });

  it('안내 주소는 팝업을 띄우고 확인 뒤에 넘어간다', async () => {
    const user = await submit('경기도 성남시 분당구 판교역로 166');

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '확인' }));

    expect(saveVacancyInput).toHaveBeenCalledWith({
      roadAddress: '경기도 성남시 분당구 판교역로 166',
      floorUnit: '',
    });
    expect(router.push).toHaveBeenCalledWith('/building-confirm');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
