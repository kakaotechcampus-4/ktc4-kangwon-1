import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Footer from '@/components/layout/Footer';

describe('바닥글', () => {
  it('약관과 처리방침 링크를 보여 준다', () => {
    render(<Footer />);
    expect(
      screen.getByRole('link', { name: '이용약관' }).getAttribute('href')
    ).toBe('/terms');
    expect(
      screen
        .getByRole('link', { name: '개인정보 처리방침' })
        .getAttribute('href')
    ).toBe('/privacy');
    expect(document.body.textContent).toContain('사업자 등록 전 시범 운영');
  });
});
