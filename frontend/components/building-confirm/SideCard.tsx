import type { ReactNode } from 'react';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

// 여백은 화면 폭에 따라 --card-pad로 바꾼다(Card 기본 p-7보다 style이 우선한다).
const CARD_STYLE = {
  padding: 'var(--card-pad)',
  borderRadius: 'var(--side-card-radius)',
  borderWidth: '0px',
};

const CARD_CLASS =
  'w-full gap-4 [--card-pad:16px] [--side-card-radius:18px] sm:gap-5 sm:[--card-pad:32px] sm:[--side-card-radius:24px]';

type SideCardProps = {
  title: string;
  items?: string[];
  children?: ReactNode;
};

export default function SideCard({ title, items, children }: SideCardProps) {
  return (
    <Card className={CARD_CLASS} style={CARD_STYLE}>
      <p
        className="text-lg font-bold break-keep sm:text-xl"
        style={{ color: colors.text.primary }}
      >
        {title}
      </p>
      {items && (
        <ul
          className="flex list-disc flex-col gap-2.5 pl-5 text-sm break-keep sm:gap-3 sm:text-base"
          style={{ color: colors.text.secondary }}
        >
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {children}
    </Card>
  );
}
