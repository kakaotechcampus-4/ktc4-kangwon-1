import type { ReactNode } from 'react';
import Link from 'next/link';
import { colors } from '@/styles/tokens';

export default function LegalLink({
  href,
  children,
}: {
  href: '/terms' | '/privacy';
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium underline underline-offset-2"
      style={{ color: colors.brand.primary }}
    >
      {children}
    </Link>
  );
}
