'use client';

import { useState, type ReactNode } from 'react';
import { colors } from '@/styles/tokens';

export type TabItem = {
  id: string;
  label: string;
  content: ReactNode;
};

type TabsProps = {
  items: TabItem[];
  defaultTabId?: string;
};

export default function Tabs({ items, defaultTabId }: TabsProps) {
  const [activeId, setActiveId] = useState(defaultTabId ?? items[0]?.id);
  const active = items.find((item) => item.id === activeId) ?? items[0];

  return (
    <div className="flex w-full flex-col items-start">
      <div
        role="tablist"
        className="flex w-full items-center gap-1 border-b px-8"
        style={{ borderColor: colors.neutral.border }}
      >
        {items.map((item) => {
          const isActive = item.id === active?.id;

          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveId(item.id)}
              className={`relative px-5 py-3.5 text-sm font-semibold transition-colors ${
                isActive ? '' : 'text-gray-500 hover:text-gray-700'
              }`}
              style={isActive ? { color: colors.brand.dark } : undefined}
            >
              {item.label}
              {isActive && (
                <span
                  className="absolute inset-x-0 -bottom-px h-0.5 rounded-full"
                  style={{ backgroundColor: colors.brand.dark }}
                />
              )}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" className="w-full">
        {active?.content}
      </div>
    </div>
  );
}
