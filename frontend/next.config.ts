import path from 'node:path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // 상위 폴더의 package-lock.json을 잘못 집지 않도록 프로젝트 뿌리를 고정합니다.
  turbopack: {
    root: path.join(__dirname),
  },
  async redirects() {
    return process.env.NEXT_PUBLIC_MOCK_MODE === 'true'
      ? []
      : [{ source: '/reports', destination: '/my/reports', permanent: false }];
  },
};

export default nextConfig;
