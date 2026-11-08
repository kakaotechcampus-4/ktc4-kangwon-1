import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TermsPage from '@/app/terms/page';

vi.mock('@/components/layout/Header', () => ({ default: () => null }));

describe('이용약관 화면', () => {
  it('만 14세 이상만 가입할 수 있다고 알린다', () => {
    render(<TermsPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: '이용약관' })
    ).toBeTruthy();
    expect(document.body.textContent).toContain('만 14세');
  });

  it('출시 전 초안임을 맨 위에 알린다', () => {
    render(<TermsPage />);
    expect(document.body.textContent).toContain('출시 전 법률 검토 중인 초안');
  });
});
