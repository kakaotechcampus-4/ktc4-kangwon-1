import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PrivacyPage from '@/app/privacy/page';

vi.mock('@/components/layout/Header', () => ({ default: () => null }));

const INVISIBLE_CODE_POINTS = [0x2060, 0x00a0];

describe('개인정보 처리방침 화면', () => {
  it('제목과 보호책임자 연락처를 보여 준다', () => {
    render(<PrivacyPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: '개인정보 처리방침' })
    ).toBeTruthy();
    expect(document.body.textContent).toContain('최용빈');
    expect(document.body.textContent).toContain('chaeum.ai@gmail.com');
    expect(document.body.textContent).toContain('chaeum_session');
  });

  it('출시 전 초안임을 알리고 법이 정한 열두 항목을 표와 함께 보여 준다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain('출시 전 법률 검토 중인 초안');
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(12);
    expect(screen.getAllByRole('table').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('rowheader').length).toBeGreaterThan(0);
  });

  it('표마다 섹션 제목을 표 이름으로 붙인다', () => {
    render(<PrivacyPage />);
    for (const name of [
      '2. 처리하는 개인정보 항목과 근거',
      '3. 보관 기간',
      '5. 처리 위탁',
      '6. 국외 이전',
    ]) {
      expect(screen.getByRole('table', { name })).toBeTruthy();
    }
  });

  it('로그인 세션은 마지막으로 쓴 때부터 14일 뒤 만료된다고 알린다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain(
      '마지막으로 쓴 때부터 14일이 지나면 만료됩니다'
    );
    expect(document.body.textContent).toContain(
      '만든 시각, 만료 시각, 마지막으로 쓴 시각'
    );
  });

  it('메일 요청의 본인 확인 방법과 질문 답을 탈퇴 전에 함께 요청하라고 알린다', () => {
    render(<PrivacyPage />);
    const text = document.body.textContent;
    expect(text).toContain(
      '카카오로 가입했다면 계정에 메일 주소가 없으니, "내 분석 기록"에서 연 분석 화면의 인터넷 주소(링크)와 그 분석에 입력한 상가 주소를 함께 보내 주세요.'
    );
    expect(text).toContain(
      '질문 답 글까지 지우려면 탈퇴 버튼을 누르지 말고 메일로 요청해 주세요. 답 글을 지운 뒤 탈퇴까지 함께 처리합니다.'
    );
  });

  it('탈퇴는 내 분석 기록 화면의 버튼으로 하고, 메일 인증 전 계정만 메일로 요청한다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain(
      '탈퇴: 내 분석 기록 화면 맨 아래의 탈퇴 버튼으로 할 수 있습니다. 메일 인증을 마치지 않은 계정은 같은 메일로 요청해 주세요.'
    );
  });

  it('운영자 이름과 시행일을 채운다', () => {
    render(<PrivacyPage />);
    const text = document.body.textContent ?? '';
    expect(text).toContain('권제후, 김온, 김은우, 김주현, 최용빈');
    expect(text).not.toContain('강유비');
    expect(text).not.toContain('김유비');
    expect(text).not.toContain('【배포일】');
    expect(text).toContain('2026년 11월 11일');
  });

  it('위탁·국외 이전 회사는 공개 문서로 확인한 값만 채우고 나머지는 확인 중으로 둔다', () => {
    render(<PrivacyPage />);
    expect(document.body.textContent).toContain(
      'AI 제공자(엘리스, OpenAI, Anthropic)에게 이미 보낸 내용'
    );
    const entrusted = screen.getByRole('table', { name: '5. 처리 위탁' });
    expect(
      within(entrusted)
        .getAllByRole('rowheader')
        .map((cell) => cell.textContent)
    ).toEqual([
      'Amazon Web Services(계약 법인 【확인 중】)',
      'Vercel Inc.',
      'Plus Five Five, Inc.(Resend)',
      'Elice Inc.(엘리스)',
      '카카오(법인명 【확인 중】)',
    ]);
    expect(document.body.textContent).toContain(
      'OpenAI·Anthropic 칸은 엘리스가 두 회사의 API를 직접 쓴다는 전제로 적었으며, 실제 중계 경로는 【확인 중】입니다.'
    );
    expect(
      within(entrusted)
        .getByRole('rowheader', { name: 'Elice Inc.(엘리스)' })
        .closest('tr')?.textContent
    ).toContain('OpenAI·Anthropic');
    const transfer = screen.getByRole('table', { name: '6. 국외 이전' });
    expect(
      within(transfer)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent)
    ).toEqual(['구분', 'Vercel', 'Resend', 'OpenAI', 'Anthropic']);
    const row = (name: string) =>
      [
        ...(within(transfer)
          .getByRole('rowheader', { name })
          .closest('tr')
          ?.querySelectorAll('td') ?? []),
      ].map((cell) => cell.textContent);
    expect(row('받는 회사 법인명')).toEqual([
      'Vercel Inc.',
      'Plus Five Five, Inc.(Resend 운영 회사)',
      '【확인 중】',
      'Anthropic PBC',
    ]);
    expect(row('받는 회사 연락처')).toEqual([
      'privacy@vercel.com',
      'support@resend.com',
      '【확인 중】',
      'privacy@anthropic.com',
    ]);
    expect(row('보관 기간')).toEqual([
      '법적·계약상 의무를 지키는 데 필요한 최소 기간',
      '메일 내용과 발송 기록 30일',
      'API 요청·응답 최대 30일(남용 감시 기록)',
      'API 요청·응답을 받은 때부터 30일 안에 삭제',
    ]);
  });

  it('입력한 상가 주소는 서버 기록에서 가리지만 앞단 서버 기록에는 남을 수 있다고 알린다', () => {
    render(<PrivacyPage />);
    const text = document.body.textContent;
    expect(text).toContain(
      '주소에 실린 로그인 코드·토큰과 건물 정보를 찾으려고 입력한 상가 주소는 가려서 남깁니다.'
    );
    expect(text).toContain(
      '앞단 서버(nginx)의 접속 기록에는 가리지 않은 인터넷 주소가 남아, 입력한 상가 주소도 함께 남을 수 있습니다.'
    );
  });

  it('괄호·가운뎃점·자리 표시가 든 낱말은 한 줄로 묶고 보이지 않는 글자는 넣지 않는다', () => {
    render(<PrivacyPage />);
    for (const word of [
      'Anthropic)에게',
      '로그아웃·탈퇴',
      '【법률 검토 중】',
    ]) {
      for (const element of screen.getAllByText(word)) {
        expect(element.className).toContain('whitespace-nowrap');
      }
    }
    const text = document.body.textContent ?? '';
    const invisible = [...text].filter((char) =>
      INVISIBLE_CODE_POINTS.includes(char.codePointAt(0) ?? 0)
    );
    expect(invisible).toEqual([]);
  });

  it('보호책임자 메일 주소를 메일 쓰기 링크로 보여 준다', () => {
    render(<PrivacyPage />);
    const links = screen.getAllByRole('link', { name: 'chaeum.ai@gmail.com' });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link.getAttribute('href')).toBe('mailto:chaeum.ai@gmail.com');
    }
  });
});
