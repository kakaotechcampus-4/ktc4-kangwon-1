'use client';

import { useState, useSyncExternalStore } from 'react';
import { X } from 'lucide-react';
import { colors } from '@/styles/tokens';

const subscribe = () => () => {};
const readWithdrawn = () =>
  new URLSearchParams(window.location.search).get('withdrawn') === '1';
const serverWithdrawn = () => false;

export default function WithdrawnNotice() {
  const withdrawn = useSyncExternalStore(
    subscribe,
    readWithdrawn,
    serverWithdrawn
  );
  const [closed, setClosed] = useState(false);

  if (!withdrawn || closed) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-50 flex justify-center px-4">
      <div
        role="status"
        className="pointer-events-auto flex items-center gap-3 rounded-xl px-5 py-3.5 shadow-lg"
        style={{
          backgroundColor: colors.neutral.white,
          border: `1px solid ${colors.neutral.border}`,
          color: colors.brand.dark,
        }}
      >
        <p className="text-15 font-semibold break-keep">
          탈퇴했어요. 계정과 로그인 정보를 지웠어요.
        </p>
        <button
          type="button"
          aria-label="알림 닫기"
          onClick={() => setClosed(true)}
          className="rounded-md p-1"
          style={{ color: colors.text.secondary }}
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
