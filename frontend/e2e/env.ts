import os from 'node:os';
import path from 'node:path';

export const API_URL = 'http://localhost:8123';
export const WEB_URL = 'http://localhost:3123';
export const E2E_DB = path.join(os.tmpdir(), 'chaeum-e2e.sqlite3');
export const E2E_USER = { email: 'e2e@example.com', password: 'e2e-pass-1234' };
export const E2E_WITHDRAW_USER = {
  email: process.env.E2E_WITHDRAW_EMAIL ?? 'e2e-withdraw@example.com',
  password: 'e2e-pass-1234',
};
export const BACKEND_DIR = path.resolve(__dirname, '..', '..', 'backend');

export function python(): string {
  const configured = process.env.E2E_PYTHON;
  if (!configured) return 'python';
  return /[\\/]/.test(configured)
    ? path.resolve(BACKEND_DIR, configured)
    : configured;
}
