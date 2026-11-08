import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PrivacyPage from '@/app/privacy/page';

vi.mock('@/components/layout/Header', () => ({ default: () => null }));

describe('개인정보 처리방침 화면', () => {
  it('제목과 보호책임자 연락처를 보여 준다', () => {
    render(<PrivacyPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: '개인정보 처리방침' })
    ).toBeTruthy();
    expect(document.body.textContent).toContain('최용빈');
    expect(document.body.textContent).toContain('privacy@chaeum-ai.kr');
    expect(document.body.textContent).toContain('chaeum_session');
  });

  it('출시 전 초안임을 알리고 법이 정한 열두 항목을 표와 함께 보여 준다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain('출시 전 법률 검토 중인 초안');
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(12);
    expect(screen.getAllByRole('table').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('rowheader').length).toBeGreaterThan(0);
  });

  it('괄호 뒤 조사, 가운뎃점으로 이은 말, 【】 자리 표시를 줄바꿈으로 가르지 않는다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain('OpenAI)\u2060에게');
    expect(document.body.textContent).toContain('로그아웃\u2060·\u2060탈퇴');
    expect(document.body.textContent).toContain('【법률\u00a0검토\u00a0중】');
  });
});
