'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Header from '@/components/layout/Header';
import RequireAuth from '@/components/auth/RequireAuth';
import FormMessage from '@/components/auth/FormMessage';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import {
  getMyAnalyses,
  withdraw,
  type MyAnalyses,
  type MyAnalysis,
} from '@/lib/api/auth';
import { clearAnalysisResult, clearRequestId } from '@/lib/api/resultStore';
import { WITHDRAWAL_EFFECT } from '@/lib/legal/terms';
import { openFresh } from '@/lib/navigation';
import {
  analysisLink,
  formatDay,
  statusLabel,
  type StatusTone,
} from '@/lib/api/analysisStatus';
import { colors } from '@/styles/tokens';

const PAGE_SIZE = 20;

const TONE_COLOR: Record<StatusTone, string> = {
  done: colors.brand.primary,
  running: colors.text.tertiary,
  waiting: colors.accent.orange,
  failed: colors.status.notRecommend,
};

export default function MyReportsPage() {
  return (
    <RequireAuth>
      <MyReports />
    </RequireAuth>
  );
}

function MyReports() {
  const [items, setItems] = useState<MyAnalysis[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const receive = useCallback((offset: number, page: MyAnalyses) => {
    setItems((previous) =>
      offset === 0 ? page.items : [...previous, ...page.items]
    );
    setTotal(page.total);
    setFailed(false);
    setLoading(false);
  }, []);

  const fail = useCallback(() => {
    setFailed(true);
    setLoading(false);
  }, []);

  /** 버튼에서 부를 때. loading 표시는 여기서 세운다. */
  const loadMore = useCallback(
    (offset: number) => {
      setLoading(true);
      getMyAnalyses({ limit: PAGE_SIZE, offset })
        .then((page) => receive(offset, page))
        .catch(fail);
    },
    [receive, fail]
  );

  useEffect(() => {
    // loading은 처음부터 true다. 상태는 응답이 온 뒤에만 바뀐다.
    let alive = true;
    getMyAnalyses({ limit: PAGE_SIZE, offset: 0 })
      .then((page) => {
        if (alive) {
          receive(0, page);
        }
      })
      .catch(() => {
        if (alive) {
          fail();
        }
      });
    return () => {
      alive = false;
    };
  }, [receive, fail]);

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="mx-auto flex w-full max-w-[880px] flex-col gap-8 px-4 pt-14 pb-24 sm:px-8">
        <div className="flex flex-col gap-3">
          <p
            className="text-sm font-bold tracking-[0.08em]"
            style={{ color: colors.brand.primary }}
          >
            MY ANALYSES
          </p>
          <h1
            className="font-extrabold tracking-[-0.04em]"
            style={{
              color: colors.brand.dark,
              fontSize: 'clamp(26px, 3vw, 42px)',
            }}
          >
            내 분석 기록
          </h1>
          <p className="text-base text-[#4B5866]">
            {total > 0
              ? `지금까지 분석한 공실 ${total}곳입니다.`
              : '분석한 공실이 여기에 쌓입니다.'}
          </p>
        </div>

        {failed ? (
          <Card className="items-start gap-4">
            <p className="text-15 text-[#4B5866]">
              기록을 불러오지 못했습니다.
            </p>
            <Button type="button" variant="outline" onClick={() => loadMore(0)}>
              다시 시도
            </Button>
          </Card>
        ) : null}

        {!failed && !loading && items.length === 0 ? <EmptyState /> : null}

        {items.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {items.map((item) => (
              <AnalysisRow key={item.request_id} item={item} />
            ))}
          </ul>
        ) : null}

        {items.length < total ? (
          <Button
            type="button"
            variant="outline"
            className="self-center"
            disabled={loading}
            onClick={() => loadMore(items.length)}
          >
            {loading ? '불러오는 중…' : '더 보기'}
          </Button>
        ) : null}

        <WithdrawSection />
      </main>
    </div>
  );
}

const WITHDRAW_WORD = '탈퇴';

function WithdrawSection() {
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleWithdraw() {
    setBusy(true);
    setError(null);
    try {
      await withdraw();
    } catch (caught) {
      setError(
        caught instanceof Error && caught.message
          ? caught.message
          : '탈퇴하지 못했어요. 잠시 후 다시 시도해 주세요.'
      );
      setBusy(false);
      return;
    }
    clearAnalysisResult();
    clearRequestId();
    openFresh('/?withdrawn=1');
  }

  return (
    <section
      aria-labelledby="withdraw-title"
      className="mt-8 flex flex-col gap-3 border-t pt-8"
      style={{ borderColor: colors.neutral.border }}
    >
      <h2
        id="withdraw-title"
        className="text-lg font-extrabold"
        style={{ color: colors.brand.dark }}
      >
        탈퇴
      </h2>
      <p className="text-sm break-keep text-[#4B5866]">{WITHDRAWAL_EFFECT}</p>
      <p className="text-sm break-keep text-[#4B5866]">
        질문 답 글도 지우려면 탈퇴하기 전에 chaeum.ai@gmail.com으로 알려 주세요.
        카카오 연결은 카카오 계정 설정에서 직접 끊어 주세요.
      </p>
      <label
        htmlFor="withdraw-confirm"
        className="text-sm font-semibold"
        style={{ color: colors.brand.dark }}
      >
        확인을 위해 &quot;{WITHDRAW_WORD}&quot;라고 입력해 주세요
      </label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          id="withdraw-confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          autoComplete="off"
          aria-describedby={error ? 'withdraw-error' : undefined}
          className="sm:max-w-[240px]"
        />
        <Button
          type="button"
          variant="outline"
          disabled={busy || confirm.trim() !== WITHDRAW_WORD}
          onClick={handleWithdraw}
          style={{
            color: colors.status.notRecommend,
            borderColor: colors.status.notRecommend,
          }}
        >
          {busy ? '탈퇴하는 중…' : '탈퇴하기'}
        </Button>
      </div>
      {error ? (
        <FormMessage tone="error" id="withdraw-error">
          {error}
        </FormMessage>
      ) : null}
    </section>
  );
}

function AnalysisRow({ item }: { item: MyAnalysis }) {
  const router = useRouter();
  const status = statusLabel(item.status);
  const link = analysisLink(item.request_id, item.status);

  return (
    <li>
      <Card className="flex-row items-center justify-between gap-4 rounded-[22px] p-6">
        <div className="flex min-w-0 flex-col gap-1.5">
          <p
            className="truncate text-xl font-extrabold tracking-[-0.02em]"
            style={{ color: colors.brand.dark }}
          >
            {item.input_address}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span style={{ color: TONE_COLOR[status.tone], fontWeight: 700 }}>
              {status.text}
            </span>
            <span className="text-[#6B7886]">{formatDay(item.created_at)}</span>
          </div>
        </div>
        {link ? (
          <Button
            type="button"
            variant="outline"
            className="shrink-0"
            onClick={() => router.push(link.href)}
          >
            {link.label}
          </Button>
        ) : null}
      </Card>
    </li>
  );
}

function EmptyState() {
  return (
    <Card className="items-start gap-4">
      <p
        className="text-xl font-extrabold tracking-[-0.02em]"
        style={{ color: colors.brand.dark }}
      >
        아직 분석한 공실이 없습니다
      </p>
      <p className="text-15 text-[#4B5866]">
        주소 하나만 넣으면 어떤 업종이 맞는지 근거와 함께 알려드립니다.
      </p>
      <Link href="/vacancy-input">
        <Button type="button" variant="primary">
          공실 분석 시작하기
        </Button>
      </Link>
    </Card>
  );
}
