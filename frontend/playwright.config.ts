import { defineConfig } from '@playwright/test';
import { API_URL, BACKEND_DIR, E2E_DB, WEB_URL, python } from './e2e/env';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  timeout: 180_000,
  workers: 1,
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: WEB_URL,
    channel: 'chrome',
    viewport: { width: 1280, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `"${python()}" -m uvicorn app.main:create_app --factory --port 8123`,
      cwd: BACKEND_DIR,
      url: `${API_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        MOCK_MODE: '1',
        SQLITE_PATH: E2E_DB,
        SESSION_COOKIE_SECURE: 'false',
        CORS_ALLOW_ORIGINS: WEB_URL,
        FRONTEND_BASE_URL: WEB_URL,
        RESEND_API_KEY: '',
        MAIL_FROM: '',
      },
    },
    {
      command: 'npm run build && npm run start -- -p 3123',
      url: WEB_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
      env: {
        NEXT_PUBLIC_API_BASE_URL: API_URL,
        NEXT_PUBLIC_MOCK_MODE: 'false',
      },
    },
  ],
});
