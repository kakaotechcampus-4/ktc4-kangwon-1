import type { ReactNode } from 'react';
import RequireAuth from '@/components/auth/RequireAuth';

/**
 * 괄호 폴더는 주소에 들어가지 않는다. /vacancy-input 같은 경로는 그대로이고
 * 가드만 한 곳에서 걸린다.
 *
 * 분석 한 번이 공공 API 100회와 모델 호출 40회를 쓴다. 비용이 실제로 발생하는
 * 지점이 여기라서, 랜딩이 아니라 이 흐름의 입구에서 로그인을 요구한다.
 */
export default function ProtectedLayout({ children }: { children: ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
