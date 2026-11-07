import { execFileSync } from 'node:child_process';
import { BACKEND_DIR, E2E_DB, E2E_USER, python } from './env';

export default function globalSetup() {
  execFileSync(
    python(),
    ['scripts/create_e2e_user.py', E2E_DB, E2E_USER.email, E2E_USER.password],
    { cwd: BACKEND_DIR, stdio: 'inherit' }
  );
}
