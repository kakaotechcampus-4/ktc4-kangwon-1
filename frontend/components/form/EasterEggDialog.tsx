'use client';

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import Button, { ButtonLink } from '@/components/ui/Button';
import type { EasterEgg } from '@/lib/easterEggs';
import { colors } from '@/styles/tokens';

type EasterEggDialogProps = {
  egg: EasterEgg;
  onClose: () => void;
};

export default function EasterEggDialog({
  egg,
  onClose,
}: EasterEggDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) {
        return;
      }
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])'
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-6"
      style={{ backgroundColor: `${colors.brand.dark}73` }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="안내"
        className="flex w-full max-w-[440px] flex-col gap-7 rounded-[24px] bg-white p-6 shadow-[0_24px_64px_rgba(16,35,58,0.24)] sm:p-8"
      >
        {egg.paragraphs.length > 0 && (
          <div className="flex flex-col gap-2.5">
            {egg.paragraphs.map((paragraph) => (
              <p
                key={paragraph}
                className="text-[17px] leading-[1.7] break-keep"
                style={{ color: colors.brand.dark }}
              >
                {paragraph}
              </p>
            ))}
          </div>
        )}
        <div className="flex flex-col gap-3">
          {egg.links.map((link) => (
            <ButtonLink
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              variant="outline"
              className="h-[52px] w-full text-base break-keep"
            >
              {link.label}
            </ButtonLink>
          ))}
          <Button
            type="button"
            autoFocus
            className="h-[52px] w-full text-base"
            onClick={onClose}
          >
            확인
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
}
