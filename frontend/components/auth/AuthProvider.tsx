'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getMe, type AuthUser } from '@/lib/api/auth';
import { onUnauthorized } from '@/lib/api/http';

/**
 * 세 가지 상태를 구분한다. loading을 따로 두지 않으면 첫 화면이 잠깐
 * "비로그인"으로 그려졌다가 바뀌어 깜빡인다.
 */
export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

type AuthValue = {
  status: AuthStatus;
  user: AuthUser | null;
  /** 로그인·로그아웃 뒤 서버 상태를 다시 읽는다. */
  refresh: () => Promise<void>;
  /** 로그아웃처럼 이미 결과를 아는 경우 즉시 비운다. */
  clear: () => void;
};

const AuthContext = createContext<AuthValue | null>(null);

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  const apply = useCallback((next: AuthUser | null) => {
    setUser(next);
    setStatus(next ? 'authenticated' : 'anonymous');
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await getMe());
    } catch {
      apply(null);
    }
  }, [apply]);

  const clear = useCallback(() => apply(null), [apply]);

  const handleUnauthorized = useCallback(
    (code: 401 | 403) => {
      if (code === 401) {
        apply(null);
      }
    },
    [apply]
  );

  useEffect(() => {
    // 첫 화면에서 한 번 서버에 묻는다. 상태는 응답이 온 뒤에 바뀐다.
    let alive = true;
    getMe()
      .then((next) => {
        if (alive) {
          apply(next);
        }
      })
      .catch(() => {
        // 서버가 잠시 끊겨도 화면은 떠야 한다. 비로그인으로 두고 가드가 처리한다.
        if (alive) {
          apply(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [apply]);

  useEffect(() => {
    // 어떤 호출이든 401을 받으면 세션이 끝난 것이다. 화면 상태를 맞춘다.
    onUnauthorized(handleUnauthorized);
    return () => onUnauthorized(null);
  }, [handleUnauthorized]);

  const value = useMemo(
    () => ({ status, user, refresh, clear }),
    [status, user, refresh, clear]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuth는 AuthProvider 안에서만 쓸 수 있습니다.');
  }
  return value;
}
