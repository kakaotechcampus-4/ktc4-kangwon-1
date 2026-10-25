import Link from 'next/link';
import Header from '@/components/layout/Header';
import { colors } from '@/styles/tokens';

/** 로그인 자리. 회원 기능이 붙기 전까지 준비 중 안내만 보여준다. */
export default function LoginPage() {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center">
        <p
          className="text-sm font-bold tracking-[0.08em]"
          style={{ color: colors.brand.primary }}
        >
          LOGIN
        </p>
        <h1
          className="text-3xl font-extrabold tracking-[-0.03em]"
          style={{ color: colors.brand.dark }}
        >
          로그인은 준비 중이에요
        </h1>
        <p className="text-base text-[#4B5866]">
          지금은 로그인 없이 바로 공실을 분석할 수 있어요.
        </p>
        <Link
          href="/vacancy-input"
          className="mt-4 inline-flex h-12 items-center rounded-xl px-6 text-base font-bold text-white transition-opacity hover:opacity-90"
          style={{ backgroundColor: colors.brand.primary }}
        >
          공실 분석 시작하기
        </Link>
      </main>
    </div>
  );
}
