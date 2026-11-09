import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import EasterEggDialog from '@/components/form/EasterEggDialog';
import type { EasterEgg } from '@/lib/easterEggs';

const egg: EasterEgg = {
  id: 'sample',
  paragraphs: ['첫째 문단...', '둘째 문단....'],
  links: [{ label: '들으러 가기', href: 'https://example.com/a' }],
};

describe('EasterEggDialog', () => {
  it('문단과 새 탭 링크를 모달로 보여 준다', () => {
    render(<EasterEggDialog egg={egg} onClose={vi.fn()} />);

    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(screen.getByText('첫째 문단...')).toBeTruthy();
    expect(screen.getByText('둘째 문단....')).toBeTruthy();

    const link = screen.getByRole('link', { name: '들으러 가기' });
    expect(link.getAttribute('href')).toBe('https://example.com/a');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('변형이 걸린 조상 밖, 문서 바로 아래에 그려 화면 전체를 덮는다', () => {
    const { container } = render(
      <EasterEggDialog egg={egg} onClose={vi.fn()} />
    );

    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(screen.getByRole('dialog').parentElement?.parentElement).toBe(
      document.body
    );
  });

  it('열리면 확인 버튼에 초점이 간다', () => {
    render(<EasterEggDialog egg={egg} onClose={vi.fn()} />);
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: '확인' })
    );
  });

  it('확인을 누르면 한 번 닫는다', async () => {
    const onClose = vi.fn();
    render(<EasterEggDialog egg={egg} onClose={onClose} />);

    await userEvent.setup().click(screen.getByRole('button', { name: '확인' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('Esc를 누르면 한 번 닫는다', () => {
    const onClose = vi.fn();
    render(<EasterEggDialog egg={egg} onClose={onClose} />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
