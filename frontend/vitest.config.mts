import { defineConfig } from 'vitest/config';
import path from 'node:path';

// tsconfig.json의 "@/*": ["./*"] 경로 별칭을 그대로 맞춘다. 이 프로젝트의
// 모든 순수 로직(어댑터, 유틸)이 그 별칭으로 서로를 import하므로, 테스트
// 러너도 같은 별칭을 풀 수 있어야 한다.
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, '.'),
    },
  },
  test: {
    environment: 'node',
  },
});
