import type { Metadata } from 'next';
import LegalDocument from '@/components/legal/LegalDocument';
import { PRIVACY } from '@/lib/legal/privacy';

export const metadata: Metadata = {
  title: '채움 · 개인정보 처리방침',
};

export default function PrivacyPage() {
  return <LegalDocument doc={PRIVACY} />;
}
