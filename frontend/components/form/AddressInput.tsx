'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { createAnalysis } from '@/lib/api/analyses';
import { saveAnalysisResult, saveRequestId } from '@/lib/api/resultStore';

export default function AddressInput() {
  const router = useRouter();
  const [roadAddress, setRoadAddress] = useState('');
  const [floorUnit, setFloorUnit] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  async function handleSubmit() {
    if (!roadAddress.trim()) {
      alert('주소를 입력해주세요');
      return;
    }

    setIsAnalyzing(true);
    try {
      // mock 옵션 없이 기본값(false)으로 호출한다 — 실제 백엔드를 부른다.
      // 테스트 단계에서 백엔드 키 없이 화면만 확인하려면 아래를
      // createAnalysis(roadAddress, { mock: true })로 임시로 바꿔서 쓴다.
      const fullAddress = floorUnit.trim()
        ? `${roadAddress} ${floorUnit}`
        : roadAddress;
      const { result, requestId } = await createAnalysis(fullAddress);

      if (result.status === 'no_data') {
        console.warn('[AddressInput] no_data:', result.limitations);
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
      console.error('[AddressInput] 분석 요청 실패:', error);
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
    <Card
      className="w-full gap-4"
      style={{
        padding: '24px',
        borderRadius: '12px',
        borderWidth: '1px',
        boxShadow: 'none',
      }}
    >
      <p className="text-xl font-bold" style={{ color: colors.brand.dark }}>
        1. 공실 주소
      </p>

      <div className="flex w-full items-start gap-4">
        <div className="flex flex-1 flex-col items-start gap-2">
          <label
            htmlFor="road-address"
            className="text-[15px] font-medium text-gray-500"
          >
            도로명 주소
          </label>
          <Input
            id="road-address"
            value={roadAddress}
            onChange={(event) => setRoadAddress(event.target.value)}
            placeholder="서울특별시 관악구 봉천로 123"
          />
        </div>
        <div className="flex flex-1 flex-col items-start gap-2">
          <label
            htmlFor="floor-unit"
            className="text-[15px] font-medium text-gray-500"
          >
            층 / 호수
          </label>
          <Input
            id="floor-unit"
            value={floorUnit}
            onChange={(event) => setFloorUnit(event.target.value)}
            placeholder="1층 101호"
          />
        </div>
      </div>

      <div className="flex w-full justify-end gap-3 pt-2">
        <Button
          type="button"
          variant="outline"
          className="text-gray-500"
          style={{ padding: '14px 24px' }}
        >
          임시 저장
        </Button>
        <Button
          type="button"
          variant="primary"
          style={{ padding: '14px 24px' }}
          disabled={isAnalyzing}
          onClick={handleSubmit}
        >
          {isAnalyzing
            ? '분석 중... (최대 1분 정도 걸릴 수 있어요)'
            : '다음 · AI 판독 결과 확인'}
        </Button>
      </div>
    </Card>
  );
}