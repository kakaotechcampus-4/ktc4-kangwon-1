import { execFileSync } from 'node:child_process';
import {
  BACKEND_DIR,
  E2E_DB,
  E2E_USER,
  E2E_WITHDRAW_USER,
  python,
} from './env';

export default function globalSetup() {
  const withdrawEmail = `e2e-withdraw-${Date.now()}@example.com`;
  process.env.E2E_WITHDRAW_EMAIL = withdrawEmail;
  for (const user of [
    E2E_USER,
    { ...E2E_WITHDRAW_USER, email: withdrawEmail },
  ]) {
    execFileSync(
      python(),
      ['scripts/create_e2e_user.py', E2E_DB, user.email, user.password],
      { cwd: BACKEND_DIR, stdio: 'inherit' }
    );
  }
}
