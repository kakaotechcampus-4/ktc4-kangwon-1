import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import AddressInput from '@/components/form/AddressInput';
import AnalysisPreviewPanel from '@/components/form/AnalysisPreviewPanel';
import { colors } from '@/styles/tokens';

export default function VacancyInputPage() {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="flex w-full flex-col items-start gap-8 px-8 py-10">
        <StepIndicator />

        <div className="flex flex-col items-start gap-3">
          <h1
            className="text-[32px] font-bold"
            style={{ color: colors.neutral.black }}
          >
            분석할 공실 정보를 입력해 주세요
          </h1>
          <p className="text-base text-gray-500">
            모든 정보를 지금 다 채울 필요는 없어요! 빠진 내용은 AI가 다음
            단계에서 다시 물어요
          </p>
        </div>

        <div className="flex w-full items-start gap-8">
          <div className="flex flex-1">
            <AddressInput />
          </div>
          <AnalysisPreviewPanel />
        </div>
      </main>
    </div>
  );
}
