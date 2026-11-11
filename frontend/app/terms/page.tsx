import type { Metadata } from 'next';
import LegalDocument from '@/components/legal/LegalDocument';
import { TERMS } from '@/lib/legal/terms';

export const metadata: Metadata = {
  title: '채움 · 이용약관',
};

export default function TermsPage() {
  return <LegalDocument doc={TERMS} />;
}
