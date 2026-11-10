import { expect, test } from '@playwright/test';
import { answerUntilDone, logIn, startAnalysis, watchErrors } from './helpers';

test('로그인부터 리포트와 내 분석 기록까지', async ({ page }) => {
  const errors = watchErrors(page);

  await page.goto('/vacancy-input');
  await expect(page).toHaveURL(/\/login/);
  await logIn(page);
  await expect(page).toHaveURL(/\/vacancy-input/);

  await startAnalysis(page);
  const requestId = new URL(page.url()).searchParams.get('id');
  await answerUntilDone(page);
  await page
    .locator('main')
    .getByText(/리포트 보기/)
    .first()
    .click();
  await expect(page).toHaveURL(/\/report/);
  await expect(page.locator('main')).toContainText('추천', { timeout: 30_000 });
  await expect(page.locator('main')).toContainText('위례광장로 199');

  await page.goto('/my/reports');
  await expect(page.locator('main')).toContainText('위례광장로 199');
  await page.getByRole('button', { name: '리포트 열기' }).first().click();
  await expect(page).toHaveURL(`/report?id=${requestId}`);
  await expect(page.locator('main')).toContainText('위례광장로 199');

  expect(errors).toEqual([]);
});

test('답변 대기 분석을 기록에서 다시 열어 마치기', async ({ browser }) => {
  const first = await browser.newContext();
  const firstPage = await first.newPage();
  await firstPage.goto('/login?next=%2Fvacancy-input');
  await logIn(firstPage);
  await expect(firstPage).toHaveURL(/\/vacancy-input/);
  await startAnalysis(firstPage);
  await expect(firstPage.getByRole('button', { name: /답변하고/ })).toBeVisible(
    { timeout: 120_000 }
  );
  const requestId = new URL(firstPage.url()).searchParams.get('id');
  await first.close();

  const second = await browser.newContext();
  const page = await second.newPage();
  const errors = watchErrors(page);
  await page.goto('/my/reports');
  await expect(page).toHaveURL(/\/login/);
  await logIn(page);
  await expect(page).toHaveURL(/\/my\/reports/);

  await page
    .locator('li')
    .filter({ hasText: '추가 답변 필요' })
    .first()
    .getByRole('button', { name: '답변하러 가기' })
    .click();
  await expect(page).toHaveURL(`/analysis-progress?id=${requestId}`);
  await expect(page.locator('main')).toContainText('위례광장로 199');

  await answerUntilDone(page);
  await page
    .locator('main')
    .getByText(/리포트 보기/)
    .first()
    .click();
  await expect(page).toHaveURL(`/report?id=${requestId}`);
  await expect(page.locator('main')).toContainText('위례광장로 199', {
    timeout: 30_000,
  });

  expect(errors).toEqual([]);
  await second.close();
});
