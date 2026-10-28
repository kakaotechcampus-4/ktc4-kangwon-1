import { pretendard } from '@/styles/fonts';
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  Check,
  FileCheck2,
  Loader2,
  MapPin,
  ShieldCheck,
} from 'lucide-react';
import Card from '@/components/ui/Card';
import ProgressBar from '@/components/ui/ProgressBar';
import { colors } from '@/styles/tokens';
import {
  LOOKUP_ORDER,
  type LookupId,
  type LookupStatus,
} from '@/lib/api/building';
import { LOOKUP_LABELS } from './labels';

const dmMono = pretendard;

const STATUS_TEXT: Record<LookupStatus, string> = {
  pending: '대기',
  loading: '조회 중',
  done: '완료',
  failed: '직접 확인 필요',
};

type BuildingLoadingProps = {
  statuses: Record<LookupId, LookupStatus>;
  floorLabel: string;
  address?: string;
  errorMessage?: string | null;
  onRetry?: () => void;
};

/** 조회 상태와 다음 행동을 한 화면에서 확인할 수 있도록 구성한다. */
export default function BuildingLoading({
  statuses,
  floorLabel,
  address,
  errorMessage,
  onRetry,
}: BuildingLoadingProps) {
  const finished = LOOKUP_ORDER.filter(
    (id) => statuses[id] === 'done' || statuses[id] === 'failed'
  ).length;
  const hasFailed = LOOKUP_ORDER.some((id) => statuses[id] === 'failed');
  const complete = finished === LOOKUP_ORDER.length;

  return (
    <section className="mx-auto flex w-full max-w-[720px] flex-col items-center gap-7 pb-6 pt-2">
      <div className="flex flex-col items-center gap-4 text-center">
        <div
          className="relative flex size-20 items-center justify-center rounded-3xl border"
          style={{
            background: `linear-gradient(145deg, ${colors.neutral.white}, ${colors.brand.primary}14)`,
            borderColor: `${colors.brand.primary}25`,
            color: colors.brand.dark,
          }}
        >
          <Building2 size={38} strokeWidth={1.5} aria-hidden="true" />
          <span
            className="absolute -bottom-1 -right-1 flex size-7 items-center justify-center rounded-full border-4"
            style={{
              backgroundColor: colors.brand.primary,
              borderColor: colors.neutral.background,
              color: colors.neutral.white,
            }}
          >
            {complete ? (
              <Check size={13} />
            ) : (
              <Loader2
                size={13}
                className="animate-spin motion-reduce:animate-none"
              />
            )}
          </span>
        </div>
        <div className="flex flex-col gap-2">
          <h1
            className="text-fluid-24-32 font-bold leading-snug"
            style={{ color: colors.text.primary }}
          >
            {complete
              ? '상가 정보를 확인할 준비가 됐어요'
              : '상가의 기본 정보를 확인하고 있어요'}
          </h1>
          <p
            className="text-sm leading-relaxed"
            style={{ color: colors.text.secondary }}
          >
            건축물대장에서 용도와 면적, 설비 정보를 가져옵니다.
          </p>
        </div>
        {address && (
          <p
            className="flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm"
            style={{
              backgroundColor: colors.neutral.white,
              borderColor: colors.neutral.border,
              color: colors.text.secondary,
            }}
          >
            <MapPin size={14} className="shrink-0" aria-hidden="true" />
            {address} · {floorLabel}
          </p>
        )}
      </div>

      <Card
        className="w-full gap-5"
        style={{
          padding: '24px',
          borderRadius: '20px',
          borderWidth: '1px',
          boxShadow: `0 12px 36px ${colors.brand.dark}08`,
        }}
      >
        <div className="flex flex-col gap-3">
          <div
            className="flex items-center justify-between gap-3"
            role="status"
          >
            <p
              className="flex items-center gap-2 text-sm font-semibold"
              style={{ color: colors.brand.dark }}
            >
              <FileCheck2 size={17} aria-hidden="true" />
              {complete ? '조회 완료' : '건축물대장 조회 중'}
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

        <ul className="flex flex-col gap-2">
          {LOOKUP_ORDER.map((id, index) => {
            const status = statuses[id];
            const active = status === 'loading';
            return (
              <li
                key={id}
                className="flex items-center gap-3 rounded-xl border p-3 transition-colors"
                style={{
                  backgroundColor: active
                    ? `${colors.brand.primary}0D`
                    : colors.neutral.white,
                  borderColor: active
                    ? `${colors.brand.primary}33`
                    : 'transparent',
                }}
              >
                <div
                  className="flex size-9 shrink-0 items-center justify-center rounded-xl"
                  style={{
                    backgroundColor:
                      status === 'failed'
                        ? `${colors.accent.orange}14`
                        : status === 'pending'
                          ? colors.neutral.background
                          : `${colors.brand.primary}12`,
                    color:
                      status === 'failed'
                        ? colors.accent.orange
                        : status === 'pending'
                          ? colors.text.tertiary
                          : colors.brand.primary,
                  }}
                >
                  {status === 'done' ? (
                    <Check size={18} strokeWidth={2.5} />
                  ) : active ? (
                    <Loader2
                      size={18}
                      className="animate-spin motion-reduce:animate-none"
                    />
                  ) : status === 'failed' ? (
                    <AlertTriangle size={18} />
                  ) : (
                    <span className={`${dmMono.className} text-xs`}>
                      {String(index + 1).padStart(2, '0')}
                    </span>
                  )}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p
                    className="text-sm font-semibold"
                    style={{
                      color:
                        status === 'pending'
                          ? colors.text.secondary
                          : colors.text.primary,
                    }}
                  >
                    {LOOKUP_LABELS[id].title}
                  </p>
                  <p
                    className="text-xs leading-relaxed"
                    style={{ color: colors.text.secondary }}
                  >
                    {LOOKUP_LABELS[id].description(floorLabel)}
                  </p>
                </div>
                <span
                  className="shrink-0 rounded-full px-2.5 py-1 text-xs font-medium"
                  style={{
                    color:
                      status === 'failed'
                        ? colors.accent.orange
                        : active
                          ? colors.brand.dark
                          : colors.text.tertiary,
                    backgroundColor: active
                      ? `${colors.brand.primary}14`
                      : 'transparent',
                  }}
                >
                  {STATUS_TEXT[status]}
                </span>
              </li>
            );
          })}
        </ul>

        {errorMessage && (
          <div
            className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between"
            role="alert"
            style={{
              backgroundColor: `${colors.accent.orange}0F`,
              borderColor: `${colors.accent.orange}40`,
            }}
          >
            <p
              className="text-sm leading-relaxed"
              style={{ color: colors.text.primary }}
            >
              {errorMessage}
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="min-h-10 shrink-0 rounded-lg border px-4 text-sm font-semibold"
                style={{
                  color: colors.brand.dark,
                  borderColor: colors.neutral.border,
                  backgroundColor: colors.neutral.white,
                }}
              >
                다시 조회
              </button>
            )}
          </div>
        )}

        <div
          className="flex items-start gap-3 rounded-xl p-4"
          style={{ backgroundColor: colors.neutral.background }}
        >
          <ArrowRight
            size={17}
            className="mt-0.5 shrink-0"
            style={{ color: colors.brand.primary }}
            aria-hidden="true"
          />
          <div className="flex flex-col gap-1">
            <p
              className="text-sm font-semibold"
              style={{ color: colors.text.primary }}
            >
              다음은 실제 상가 정보와 맞는지 확인해요
            </p>
            <p
              className="text-xs leading-relaxed"
              style={{ color: colors.text.secondary }}
            >
              {hasFailed
                ? '불러오지 못한 항목은 다음 화면에서 직접 입력할 수 있어요.'
                : '불러온 정보가 실제와 다르면 다음 화면에서 고칠 수 있어요.'}
            </p>
          </div>
        </div>
      </Card>
      <p
        className="flex items-center gap-1.5 text-xs"
        style={{ color: colors.text.tertiary }}
      >
        <ShieldCheck size={14} aria-hidden="true" /> 국토교통부 건축물대장 HUB
        기준
      </p>
    </section>
  );
}
