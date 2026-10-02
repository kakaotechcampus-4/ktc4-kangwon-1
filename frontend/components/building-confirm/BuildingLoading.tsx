import { DM_Mono } from 'next/font/google';
import { AlertTriangle, Check, Loader2 } from 'lucide-react';
import Card from '@/components/ui/Card';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import {
  LOOKUP_ORDER,
  type LookupId,
  type LookupStatus,
} from '@/lib/api/building';
import { LOOKUP_LABELS } from './labels';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

const STATUS_TEXT: Record<LookupStatus, string> = {
  pending: '대기',
  loading: '조회 중',
  done: '완료',
  failed: '실패',
};

type BuildingLoadingProps = {
  statuses: Record<LookupId, LookupStatus>;
  floorLabel: string;
};

/** 건축물대장 4개 항목 조회 진행 상황. 실패한 항목은 확인 화면에서 직접 채운다. */
export default function BuildingLoading({
  statuses,
  floorLabel,
}: BuildingLoadingProps) {
  const finished = LOOKUP_ORDER.filter(
    (id) => statuses[id] === 'done' || statuses[id] === 'failed'
  ).length;

  return (
    <Card
      className="w-full max-w-[1048px] gap-6"
      style={{ padding: '32px', borderRadius: '12px', borderWidth: '1px' }}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <p className="text-xl font-bold" style={{ color: colors.brand.dark }}>
            조회 중
          </p>
          <p
            className={`${dmMono.className} text-sm`}
            style={{ color: colors.text.secondary }}
          >
            {finished} / {LOOKUP_ORDER.length}
          </p>
        </div>
        <ProgressBar value={(finished / LOOKUP_ORDER.length) * 100} />
      </div>

      <ul className="flex flex-col">
        {LOOKUP_ORDER.map((id, index) => (
          <li
            key={id}
            className="flex items-start gap-4 py-5"
            style={{
              borderTop:
                index === 0 ? 'none' : `1px solid ${colors.neutral.border}`,
            }}
          >
            <StatusIcon status={statuses[id]} />
            <div className="flex flex-1 flex-col gap-1">
              <p
                className="text-base font-semibold"
                style={{
                  color:
                    statuses[id] === 'pending'
                      ? colors.text.tertiary
                      : colors.text.primary,
                }}
              >
                {LOOKUP_LABELS[id].title}
              </p>
              <p className="text-sm" style={{ color: colors.text.secondary }}>
                {LOOKUP_LABELS[id].description(floorLabel)}
              </p>
            </div>
            <p
              className="text-sm"
              style={{
                color:
                  statuses[id] === 'failed'
                    ? colors.accent.orange
                    : colors.text.tertiary,
              }}
            >
              {STATUS_TEXT[statuses[id]]}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function StatusIcon({ status }: { status: LookupStatus }) {
  const base = 'flex size-9 shrink-0 items-center justify-center rounded-full';

  if (status === 'done') {
    return (
      <div
        className={base}
        style={{ backgroundColor: `${colors.brand.primary}1F` }}
      >
        <Check size={18} strokeWidth={3} color={colors.brand.primary} />
      </div>
    );
  }
  if (status === 'loading') {
    return (
      <div
        className={base}
        style={{ backgroundColor: `${colors.brand.primary}0F` }}
      >
        <Loader2
          size={18}
          className="animate-spin"
          style={{ color: colors.brand.primary }}
        />
      </div>
    );
  }
  if (status === 'failed') {
    return (
      <div
        className={base}
        style={{ backgroundColor: `${colors.accent.orange}1A` }}
      >
        <AlertTriangle size={17} color={colors.accent.orange} />
      </div>
    );
  }
  return (
    <div
      className={`${base} border`}
      style={{
        borderColor: colors.neutral.border,
        backgroundColor: colors.neutral.white,
      }}
    />
  );
}
