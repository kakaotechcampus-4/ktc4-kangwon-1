import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BuildingConfirmPage from './page';
import { AnalysisApiError, startAnalysis } from '@/lib/api/analyses';
import { OutsideServiceAreaError, fetchBuildingInfo } from '@/lib/api/building';
import {
  LOOKUP_ERROR_NOTE,
  emptyBuildingInfo,
} from '@/lib/api/buildingRegistry';
import { ApiError } from '@/lib/api/http';
import { saveVacancyInput } from '@/lib/api/resultStore';

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/styles/fonts', () => ({
  pretendard: { className: '', variable: '' },
}));
vi.mock('@/components/layout/Header', () => ({ default: () => null }));
vi.mock('@/lib/api/building', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/building')>()),
  fetchBuildingInfo: vi.fn(),
}));
vi.mock('@/lib/api/analyses', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/analyses')>()),
  startAnalysis: vi.fn(),
}));

const ADDRESS = '서울 송파구 위례광장로 199';
const START = '맞아요 · 이대로 분석하기';

beforeEach(() => {
  vi.clearAllMocks();
  saveVacancyInput({ roadAddress: ADDRESS, floorUnit: '1층' });
  vi.mocked(fetchBuildingInfo).mockResolvedValue(
    emptyBuildingInfo(ADDRESS, '1층', '')
  );
});

async function chooseParking() {
  const user = userEvent.setup();
  const start = await screen.findByRole(
    'button',
    { name: START },
    { timeout: 3000 }
  );
  const parking = screen.getByRole('radiogroup', { name: '주차 가능 여부' });
  await user.click(
    Array.from(parking.querySelectorAll('[role="radio"]')).find(
      (radio) => radio.textContent === '가능'
    ) as HTMLElement
  );
  return { user, start };
}

describe('상가 정보 확인 화면', () => {
  it('입력한 주소가 없으면 주소 입력으로 돌아간다', async () => {
    sessionStorage.clear();
    render(<BuildingConfirmPage />);
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/vacancy-input')
    );
    expect(fetchBuildingInfo).not.toHaveBeenCalled();
  });

  it('주차를 고르기 전에는 분석을 시작할 수 없다', async () => {
    render(<BuildingConfirmPage />);
    const start = await screen.findByRole(
      'button',
      { name: START },
      { timeout: 3000 }
    );
    expect((start as HTMLButtonElement).disabled).toBe(true);
    await chooseParking();
    expect((start as HTMLButtonElement).disabled).toBe(false);
  });

  it('분석을 시작하면 층과 함께 요청하고 진행 화면으로 간다', async () => {
    vi.mocked(startAnalysis).mockResolvedValue({
      request_id: 'r1',
      facilitiesDropped: false,
    } as Awaited<ReturnType<typeof startAnalysis>>);
    render(<BuildingConfirmPage />);
    const { user, start } = await chooseParking();
    await user.click(start);
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith('/analysis-progress?id=r1')
    );
    expect(startAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({
        address: `${ADDRESS} 1층`,
        allowQuestions: true,
      })
    );
  });

  it('분석 시작이 거절되면 잠시 후 다시 시도하라고 알린다', async () => {
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(startAnalysis).mockRejectedValue(
      new ApiError(429, '동시에 실행할 수 있는 분석 수를 넘었습니다.')
    );
    render(<BuildingConfirmPage />);
    const { user, start } = await chooseParking();
    await user.click(start);
    await waitFor(() =>
      expect(alert).toHaveBeenCalledWith('잠시 후 다시 시도해주세요.')
    );
    expect(router.push).not.toHaveBeenCalled();
  });

  it('건축물대장 조회가 오래 걸려 멈추면 안내와 다시 조회를 보여 준다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const notice =
      '건축물대장 조회가 오래 걸려 멈췄어요. 잠시 후 다시 시도해 주세요.';
    vi.mocked(fetchBuildingInfo).mockRejectedValueOnce(
      new ApiError(504, notice)
    );
    render(<BuildingConfirmPage />);
    expect(
      await screen.findByText('건축물대장 조회가 오래 걸려 멈췄어요')
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain('준비가 됐어요');
    expect(document.body.textContent).not.toContain('다음 화면에서');
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '다시 조회' }));
    await waitFor(() => expect(fetchBuildingInfo).toHaveBeenCalledTimes(2));
  });

  it('시간 초과 안내에서 직접 입력을 골라 분석을 이어 간다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(fetchBuildingInfo).mockRejectedValueOnce(
      new ApiError(504, '건축물대장 조회가 오래 걸려 멈췄어요.')
    );
    render(<BuildingConfirmPage />);
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: '직접 입력하고 계속' }));
    expect(await screen.findByRole('button', { name: START })).toBeTruthy();
    expect(document.body.textContent).toContain(LOOKUP_ERROR_NOTE);
    expect(fetchBuildingInfo).toHaveBeenCalledTimes(1);
  });

  it('입력값이 잘못돼 거절되면 입력을 확인하라고 알린다', async () => {
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const message =
      '요청 값이 올바르지 않아 처리하지 못했어요. 입력한 정보를 확인해 주세요.';
    vi.mocked(startAnalysis).mockRejectedValue(
      new AnalysisApiError(422, message)
    );
    render(<BuildingConfirmPage />);
    const { user, start } = await chooseParking();
    await user.click(start);
    await waitFor(() => expect(alert).toHaveBeenCalledWith(message));
  });

  it('서울 밖 주소면 확인 카드 대신 다시 입력하라는 안내를 보여 준다', async () => {
    const busan = '부산 해운대구 해운대로 264';
    saveVacancyInput({ roadAddress: busan, floorUnit: '1층' });
    vi.mocked(fetchBuildingInfo).mockRejectedValueOnce(
      new OutsideServiceAreaError('지금은 서울 상가만 분석할 수 있어요.')
    );
    render(<BuildingConfirmPage />);
    expect(
      await screen.findByRole('heading', { name: '이 주소는 분석할 수 없어요' })
    ).toBeTruthy();
    expect(
      screen.getByText('채움은 지금 서울에 있는 상가만 분석해요.')
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', {
        name: '지금은 서울 상가만 분석할 수 있어요',
      })
    ).toBeTruthy();
    expect(
      screen.getByText(
        '상권·인구 자료가 서울시 공공데이터라서 서울 밖 주소는 정확하게 분석할 수 없어요. 서울에 있는 상가 주소로 다시 입력해 주세요.'
      )
    ).toBeTruthy();
    expect(screen.getByRole('heading', { name: busan })).toBeTruthy();
    expect(screen.getByText('서울 밖 주소')).toBeTruthy();
    expect(
      screen
        .getByRole('link', { name: '주소 다시 입력하기' })
        .getAttribute('href')
    ).toBe('/vacancy-input');
    expect(
      screen.getByRole('link', { name: '홈으로' }).getAttribute('href')
    ).toBe('/');
    expect(
      screen.queryByRole('button', { name: /이대로 분석하기/ })
    ).toBeNull();
    expect(screen.getByText('왜 서울만 분석하나요?')).toBeTruthy();
    for (const reason of [
      '상권·유동인구 자료가 서울시 열린데이터광장 자료예요.',
      '서울 밖은 같은 기준의 자료가 없어 결과를 믿기 어려워요.',
      '다른 지역은 아직 준비 중이에요.',
    ]) {
      expect(screen.getByText(reason)).toBeTruthy();
    }
  });

  it('다시 조회도 오래 걸리면 직접 입력 화면으로 넘어간다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const notice =
      '건축물대장 조회가 오래 걸려 멈췄어요. 잠시 후 다시 시도해 주세요.';
    vi.mocked(fetchBuildingInfo).mockRejectedValue(new ApiError(504, notice));
    render(<BuildingConfirmPage />);
    await userEvent
      .setup()
      .click(await screen.findByRole('button', { name: '다시 조회' }));
    const start = await screen.findByRole('button', { name: START });
    expect(document.body.textContent).toContain(LOOKUP_ERROR_NOTE);
    expect((start as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole('textbox', { name: '전용면적' })).toBeTruthy();
  });
});
