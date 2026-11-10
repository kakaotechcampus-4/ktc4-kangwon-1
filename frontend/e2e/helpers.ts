import { expect, type Page } from '@playwright/test';
import { E2E_USER } from './env';

export const ADDRESS = '서울 송파구 위례광장로 199';
export const FLOOR = '1층';

export function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (
      message.type() === 'error' &&
      !message.text().startsWith('Failed to load resource')
    ) {
      errors.push(`console: ${message.text()}`);
    }
  });
  page.on('response', (response) => {
    const signedOutCheck =
      response.status() === 401 && response.url().includes('/auth/me');
    if (response.status() >= 400 && !signedOutCheck) {
      errors.push(`${response.status()} ${response.url()}`);
    }
  });
  return errors;
}

export async function logIn(page: Page) {
  await page.getByLabel('이메일', { exact: true }).fill(E2E_USER.email);
  await page.getByLabel('비밀번호', { exact: true }).fill(E2E_USER.password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
}

export async function startAnalysis(page: Page) {
  const inputs = page.locator('main input');
  await inputs.nth(0).fill(ADDRESS);
  await inputs.nth(1).fill(FLOOR);
  await page.getByRole('button', { name: /다음/ }).click();
  await expect(page).toHaveURL(/\/building-confirm/);

  const start = page.getByRole('button', { name: '맞아요 · 이대로 분석하기' });
  await expect(start).toBeVisible({ timeout: 60_000 });
  const area = page.getByPlaceholder(/275\.49/);
  if (await area.count()) await area.fill('85');
  for (const name of ['배기(덕트)', '주방', '급배수']) {
    await page
      .getByRole('radiogroup', { name })
      .getByRole('radio', { name: '있음' })
      .click();
  }
  const parking = page.getByRole('radiogroup', { name: '주차 가능 여부' });
  if (await parking.count()) {
    await parking.getByRole('radio', { name: '가능' }).click();
  }
  await start.click();
  await expect(page).toHaveURL(/\/analysis-progress\?id=/, { timeout: 30_000 });
}

function answerFor(question: string) {
  if (/설비|배기|주방|급배수/.test(question)) {
    return '배기 덕트, 주방, 급배수 모두 있어요';
  }
  if (/면적/.test(question)) return '85';
  if (/층/.test(question)) return FLOOR;
  return '잘 모르겠어요';
}

export async function answerUntilDone(page: Page) {
  const submit = page.getByRole('button', { name: /답변하고/ });
  const report = page.locator('main').getByText(/리포트 보기/);
  await expect(submit.or(report).first()).toBeVisible({ timeout: 120_000 });
  while (await submit.isVisible()) {
    const direct = page.getByRole('button', { name: '직접 입력', exact: true });
    for (const button of await direct.all()) await button.click();
    const answer = answerFor(await page.locator('main').innerText());
    const fields = page.locator(
      'main textarea, main input:not([type="radio"]):not([type="checkbox"])'
    );
    for (const field of await fields.all()) {
      if (
        (await field.isVisible()) &&
        (await field.isEditable()) &&
        !(await field.inputValue())
      ) {
        await field.fill(answer);
      }
    }
    await submit.click();
    await expect(submit.or(report).first()).toBeVisible({ timeout: 120_000 });
    if (await report.first().isVisible()) break;
  }
  await expect(report.first()).toBeVisible({ timeout: 120_000 });
}
