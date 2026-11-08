import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BACKEND_DIR, python } from './env';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('E2E 실행 경로', () => {
  it('서버 폴더는 실행 위치와 상관없이 저장소의 backend다', () => {
    expect(BACKEND_DIR).toBe(path.resolve(__dirname, '..', '..', 'backend'));
  });

  it('파이썬 명령 이름만 주면 그대로 쓴다', () => {
    vi.stubEnv('E2E_PYTHON', 'python3');
    expect(python()).toBe('python3');
  });

  it('경로로 주면 backend 기준으로 푼다', () => {
    vi.stubEnv('E2E_PYTHON', '.venv/Scripts/python.exe');
    expect(python()).toBe(
      path.resolve(BACKEND_DIR, '.venv/Scripts/python.exe')
    );
  });

  it('윈도우 경로도 backend 기준으로 푼다', () => {
    vi.stubEnv('E2E_PYTHON', '.venv\\Scripts\\python.exe');
    expect(python()).toBe(
      path.resolve(BACKEND_DIR, '.venv\\Scripts\\python.exe')
    );
  });

  it('지정하지 않으면 python을 쓴다', () => {
    vi.stubEnv('E2E_PYTHON', '');
    expect(python()).toBe('python');
  });
});
