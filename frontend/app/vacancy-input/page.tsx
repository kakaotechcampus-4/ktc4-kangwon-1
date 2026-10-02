'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import AddressInput from '@/components/form/AddressInput';
import RadiusInput from '@/components/form/RadiusInput';
import FormActions from '@/components/form/FormActions';
import AnalysisPreviewPanel from '@/components/form/AnalysisPreviewPanel';
import { colors } from '@/styles/tokens';
import { saveVacancyInput } from '@/lib/api/resultStore';

export default function VacancyInputPage() {
  const router = useRouter();
  const [roadAddress, setRoadAddress] = useState('');
  const [floorUnit, setFloorUnit] = useState('');
  // AnalysisPreviewPanel의 "반경 Nm" 문구도 같은 값을 보여줘야 해서
  // 이 페이지에서 들고 있는다. 분석 요청 시(상가 정보 확인 화면) 숫자로
  // 바꿔 radius_m으로 보낸다.
  const [radius, setRadius] = useState('');

  // 버튼이 공실 주소 카드 밖으로 나오면서(반경 입력 카드까지 아우르는
  // 공통 액션이 되어) 제출 로직도 AddressInput에서 이 페이지로 옮겨왔다.
  // 분석 요청은 다음 화면(상가 정보 확인)의 확인 버튼에서 보내므로, 여기서는
  // 입력값만 저장하고 넘어간다.
  function handleSubmit() {
    if (!roadAddress.trim()) {
      alert('주소를 입력해주세요');
      return;
    }

    saveVacancyInput({ roadAddress, floorUnit, radius });
    router.push('/building-confirm');
  }

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="flex w-full flex-col items-start gap-8 px-8 py-10">
        <StepIndicator currentStep={1} />

        <div className="flex flex-col items-start gap-3">
          <h1
            className="text-32 font-bold"
            style={{ color: colors.neutral.black }}
          >
            분석할 공실 정보를 입력해 주세요
          </h1>
          <p className="text-base text-gray-500">
            모든 정보를 지금 다 채울 필요는 없어요! 빠진 내용은 AI가 다음
            단계에서 다시 물어요
          </p>
        </div>

        <div className="flex w-full flex-col items-start gap-8 md:flex-row">
          <div className="flex w-full flex-col gap-6 md:flex-1">
            <AddressInput
              roadAddress={roadAddress}
              onRoadAddressChange={setRoadAddress}
              floorUnit={floorUnit}
              onFloorUnitChange={setFloorUnit}
            />
            <RadiusInput value={radius} onChange={setRadius} />
            <FormActions isAnalyzing={false} onSubmit={handleSubmit} />
          </div>
          <AnalysisPreviewPanel radius={radius} />
        </div>
      </main>
    </div>
  );
}
