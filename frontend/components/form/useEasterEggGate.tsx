'use client';

import { useCallback, useState, type ReactNode } from 'react';
import EasterEggDialog from '@/components/form/EasterEggDialog';
import { findEasterEgg, type EasterEgg } from '@/lib/easterEggs';

type PendingEgg = { egg: EasterEgg; proceed: () => void };

export function useEasterEggGate(): {
  gate: (address: string, proceed: () => void) => void;
  dialog: ReactNode;
} {
  const [pending, setPending] = useState<PendingEgg | null>(null);

  const gate = useCallback((address: string, proceed: () => void) => {
    const egg = findEasterEgg(address);
    if (egg) {
      setPending({ egg, proceed });
    } else {
      proceed();
    }
  }, []);

  const close = useCallback(() => {
    if (pending) {
      setPending(null);
      pending.proceed();
    }
  }, [pending]);

  const dialog = pending ? (
    <EasterEggDialog egg={pending.egg} onClose={close} />
  ) : null;

  return { gate, dialog };
}
