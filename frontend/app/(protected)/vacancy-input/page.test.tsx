import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VacancyInputPage from '@/app/(protected)/vacancy-input/page';
import { saveVacancyInput } from '@/lib/api/resultStore';

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/lib/api/resultStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/resultStore')>()),
  saveVacancyInput: vi.fn(),
}));

async function submit(address: string) {
  const user = userEvent.setup();
  render(<VacancyInputPage />);
  await user.type(
    screen.getByRole('textbox', { name: /도로명|주소/ }),
    address
  );
  await user.click(screen.getByRole('button', { name: /다음/ }));
  return user;
}

describe('공실 입력 제출', () => {
  beforeEach(() => vi.clearAllMocks());

  it('보통 주소는 팝업 없이 바로 넘어간다', async () => {
    await submit('서울 강남구 테헤란로 152');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(router.push).toHaveBeenCalledWith('/building-confirm');
  });

  it('안내 주소는 팝업을 띄우고 확인 뒤에 같은 값으로 넘어간다', async () => {
    const user = await submit('대전광역시 유성구 대학로 99');

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '확인' }));

    expect(saveVacancyInput).toHaveBeenCalledWith({
      roadAddress: '대전광역시 유성구 대학로 99',
      floorUnit: '',
    });
    expect(router.push).toHaveBeenCalledWith('/building-confirm');
  });

  it('팝업이 떠 있는 동안 다시 제출해도 넘어가지 않는다', async () => {
    const user = await submit('대전광역시 유성구 대학로 99');

    const input = screen.getByRole('textbox', { name: /도로명|주소/ });
    await user.clear(input);
    await user.type(input, '서울 강남구 테헤란로 152');
    await user.click(screen.getByRole('button', { name: /다음|분석 시작/ }));

    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(saveVacancyInput).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it('Esc로 닫아도 원래 값으로 넘어간다', async () => {
    const user = await submit('대전광역시 유성구 대학로 99');

    await user.keyboard('{Escape}');

    expect(saveVacancyInput).toHaveBeenCalledTimes(1);
    expect(saveVacancyInput).toHaveBeenCalledWith(
      expect.objectContaining({
        roadAddress: '대전광역시 유성구 대학로 99',
        floorUnit: '',
      })
    );
    expect(router.push).toHaveBeenCalledWith('/building-confirm');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
