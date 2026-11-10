import { expect, test, type Page } from '@playwright/test';
import { answerUntilDone, logIn, startAnalysis, watchErrors } from './helpers';

test.use({ viewport: { width: 390, height: 844 } });

async function expectNoHorizontalScroll(page: Page) {
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    inner: window.innerWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.inner);
}

test('폰 화면에서 로그인부터 리포트와 로그아웃까지', async ({ page }) => {
  const errors = watchErrors(page);

  await page.goto('/');
  await expect(page.getByRole('link', { name: '로그인' })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.getByRole('link', { name: '로그인' }).click();
  await expect(page).toHaveURL(/\/login/);
  await logIn(page);
  await expect(
    page.getByRole('button', { name: '내 계정 메뉴' })
  ).toBeVisible();

  await page.goto('/vacancy-input');
  await expect(page.locator('main input').first()).toBeVisible();
  await expectNoHorizontalScroll(page);

  await startAnalysis(page);
  await expect(page).toHaveURL(/\/analysis-progress\?id=/);
  await expectNoHorizontalScroll(page);
  await answerUntilDone(page);
  await page
    .locator('main')
    .getByText(/리포트 보기/)
    .first()
    .click();
  await expect(page).toHaveURL(/\/report/);
  await expect(page.locator('main')).toContainText('위례광장로 199', {
    timeout: 30_000,
  });
  await expectNoHorizontalScroll(page);

  await page.getByRole('button', { name: '내 계정 메뉴' }).click();
  await page.getByRole('menuitem', { name: '내 분석 기록' }).click();
  await expect(page).toHaveURL(/\/my\/reports/);
  await expect(page.locator('main')).toContainText('위례광장로 199');
  await expectNoHorizontalScroll(page);

  await page.getByRole('button', { name: '내 계정 메뉴' }).click();
  await page.getByRole('menuitem', { name: '로그아웃' }).click();
  await expect(page.getByRole('link', { name: '로그인' })).toBeVisible();

  expect(errors).toEqual([]);
});
