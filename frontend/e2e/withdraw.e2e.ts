import { expect, test, type Page } from '@playwright/test';
import { E2E_WITHDRAW_USER } from './env';

async function logInAsWithdrawUser(page: Page) {
  await page.goto('/login');
  await page
    .getByLabel('이메일', { exact: true })
    .fill(E2E_WITHDRAW_USER.email);
  await page
    .getByLabel('비밀번호', { exact: true })
    .fill(E2E_WITHDRAW_USER.password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
}

test('내 분석 기록에서 탈퇴하면 같은 계정으로 다시 로그인할 수 없다', async ({
  page,
}) => {
  await logInAsWithdrawUser(page);
  await expect(page).not.toHaveURL(/\/login/);

  await page.goto('/my/reports');
  await expect(
    page.getByRole('heading', { level: 1, name: '내 분석 기록' })
  ).toBeVisible();
  const withdrawButton = page.getByRole('button', { name: '탈퇴하기' });
  await expect(withdrawButton).toBeDisabled();
  await page.getByLabel('확인을 위해 "탈퇴"라고 입력해 주세요').fill('탈퇴');
  await withdrawButton.click();

  await expect(
    page.getByText('탈퇴했어요. 계정과 로그인 정보를 지웠어요.')
  ).toBeVisible();
  await expect(page).toHaveURL(/^http:\/\/localhost:3123\/$/);
  await expect(page.getByRole('link', { name: '로그인' })).toBeVisible();

  await page.goBack();
  await expect(page).not.toHaveURL(/\/my\/reports/);

  await logInAsWithdrawUser(page);
  await expect(
    page.locator('[role="alert"]:not(#__next-route-announcer__)')
  ).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});
