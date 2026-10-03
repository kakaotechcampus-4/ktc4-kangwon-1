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
import { createAnalysis } from '@/lib/api/analyses';
import { saveAnalysisResult, saveRequestId } from '@/lib/api/resultStore';

export default function VacancyInputPage() {
  const router = useRouter();
  const [roadAddress, setRoadAddress] = useState('');
  const [floorUnit, setFloorUnit] = useState('');
  // AnalysisPreviewPanel의 "반경 Nm" 문구도 같은 값을 보여줘야 해서
  // 이 페이지에서 들고 있는다. 백엔드 계약에 radius가 추가되기 전까지는
  // 화면 표시에만 쓰고 분석 요청에는 보내지 않는다.
  const [radius, setRadius] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // 버튼이 공실 주소 카드 밖으로 나오면서(반경 입력 카드까지 아우르는
  // 공통 액션이 되어) 제출 로직도 AddressInput에서 이 페이지로 옮겨왔다.
  async function handleSubmit() {
    if (!roadAddress.trim()) {
      alert('주소를 입력해주세요');
      return;
    }

    setIsAnalyzing(true);
    try {
      // mock 옵션 없이 기본값(false)으로 호출한다 — 실제 백엔드를 부른다.
      // 테스트 단계에서 백엔드 키 없이 화면만 확인하려면 아래를
      // createAnalysis(fullAddress, { mock: true })로 임시로 바꿔서 쓴다.
      const fullAddress = floorUnit.trim()
        ? `${roadAddress} ${floorUnit}`
        : roadAddress;
      const { result, requestId } = await createAnalysis(fullAddress);

      if (result.status === 'no_data') {
        console.warn('[VacancyInputPage] no_data:', result.limitations);
        alert(
          [
            '이 주소에서는 추천할 업종을 찾지 못했습니다.',
            ...result.limitations,
          ].join('\n')
        );
        return;
      }

      saveRequestId(requestId);
      saveAnalysisResult(result);
      router.push('/report');
    } catch (error) {
      console.error('[VacancyInputPage] 분석 요청 실패:', error);
      const message =
        error instanceof Error
          ? error.message
          : '분석 요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
      alert(message);
    } finally {
      // 성공 시엔 위에서 이미 페이지를 이동하므로, 여기 도달하는 건
      // 실패했을 때뿐이다.
      setIsAnalyzing(false);
    }
  }

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

        <div className="flex w-full flex-col items-start gap-8 md:flex-row">
          <div className="flex w-full flex-col gap-6 md:flex-1">
            <AddressInput
              roadAddress={roadAddress}
              onRoadAddressChange={setRoadAddress}
              floorUnit={floorUnit}
              onFloorUnitChange={setFloorUnit}
            />
            <RadiusInput value={radius} onChange={setRadius} />
            <FormActions isAnalyzing={isAnalyzing} onSubmit={handleSubmit} />
          </div>
          <AnalysisPreviewPanel radius={radius} />
        </div>
      </main>
    </div>
  );
}
