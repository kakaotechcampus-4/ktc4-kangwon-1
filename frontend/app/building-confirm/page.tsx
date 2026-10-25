'use client';

import { mockProperty } from '@/lib/mockData/property';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/layout/Header';
import StepIndicator from '@/components/form/StepIndicator';
import FlowPageTitle from '@/components/form/FlowPageTitle';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import Input from '@/components/ui/Input';
import BuildingLoading from '@/components/building-confirm/BuildingLoading';
import BuildingSummaryHeader from '@/components/building-confirm/BuildingSummaryHeader';
import BuildingFieldRow from '@/components/building-confirm/BuildingFieldRow';
import ParkingSelector from '@/components/building-confirm/ParkingSelector';
import SegmentedSelector from '@/components/building-confirm/SegmentedSelector';
import ConfirmSidePanel from '@/components/building-confirm/ConfirmSidePanel';
import {
  FACILITY_LABELS,
  FACILITY_SHORT_LABELS,
  PARKING_LABELS,
  floorFromUnit,
  formatArea,
} from '@/components/building-confirm/labels';
import { colors } from '@/styles/tokens';
import { startAnalysis } from '@/lib/api/analyses';
import { MOCK_MODE } from '@/lib/api/mockMode';
import {
  LOOKUP_ORDER,
  SEWAGE_OPTIONS,
  editField,
  fetchBuildingInfo,
  type BuildingInfo,
  type LookupId,
  type LookupStatus,
  type NeighborhoodFacility,
  type SewageTreatment,
} from '@/lib/api/building';
import {
  clearAnalysisResult,
  clearRequestId,
  loadVacancyInput,
  saveConfirmedBuilding,
  saveRequestId,
  type VacancyInput,
} from '@/lib/api/resultStore';

const INITIAL_STATUSES = Object.fromEntries(
  LOOKUP_ORDER.map((id) => [id, 'pending'])
) as Record<LookupId, LookupStatus>;

// 조회가 끝난 뒤 4 / 4 완료 상태를 잠깐 보여주고 확인 화면으로 넘어간다.
const CONFIRM_DELAY_MS = 500;

const FACILITY_OPTIONS = (
  Object.keys(FACILITY_SHORT_LABELS) as NeighborhoodFacility[]
).map((value) => ({ value, label: FACILITY_SHORT_LABELS[value] }));

// 반경 입력칸 값 — 비어 있거나 양의 정수가 아니면 보내지 않는다(서버 기본 반경).
function parseRadius(text: string): number | undefined {
  const trimmed = text.trim();
  const value = Number(trimmed);
  return trimmed && Number.isInteger(value) && value > 0 ? value : undefined;
}

// 화면 확인용: ?mockFail=floor,sewage 처럼 넘기면 그 조회를 일부러 실패시킨다.
function mockFailLookups(search: string): LookupId[] {
  const raw = new URLSearchParams(search).get('mockFail') ?? '';
  return raw
    .split(',')
    .filter((id): id is LookupId => LOOKUP_ORDER.includes(id as LookupId));
}

export default function BuildingConfirmPage() {
  const router = useRouter();
  const [input, setInput] = useState<VacancyInput | null>(null);
  const [statuses, setStatuses] = useState(INITIAL_STATUSES);
  const [building, setBuilding] = useState<BuildingInfo | null>(null);
  // 전용면적 입력 중인 문자열("275." 같은 중간 값)을 숫자 필드와 따로 든다.
  const [areaText, setAreaText] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    // 개발 환경에서 조회 중 화면을 고정해 디자인을 확인한다.
    if (
      process.env.NODE_ENV === 'development' &&
      new URLSearchParams(window.location.search).get('previewLoading') === '1'
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInput({
        roadAddress: mockProperty.address,
        floorUnit: mockProperty.floorUnit,
        radius: String(mockProperty.radiusM),
      });
      setStatuses({
        title: 'done',
        floor: 'done',
        exclusiveArea: 'loading',
        sewage: 'pending',
      });
      return;
    }
    // sessionStorage는 브라우저 전용이라 마운트 후 한 번만 읽는다.
    const saved = loadVacancyInput();
    if (!saved) {
      router.replace('/vacancy-input');
      return;
    }
    setInput(saved);

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    fetchBuildingInfo(saved.roadAddress, {
      signal: controller.signal,
      failLookups: mockFailLookups(window.location.search),
      onStepChange: (id, status) =>
        setStatuses((prev) => ({ ...prev, [id]: status })),
    })
      .then((info) => {
        timer = setTimeout(() => {
          setBuilding(info);
          setAreaText(info.exclusiveAreaM2.value?.toString() ?? '');
        }, CONFIRM_DELAY_MS);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        console.error('[BuildingConfirmPage] 건축물대장 조회 실패:', error);
      });

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [router]);

  function updateBuilding(patch: Partial<BuildingInfo>) {
    setBuilding((prev) => (prev ? { ...prev, ...patch } : prev));
  }

  function handleAreaChange(text: string) {
    if (!building) {
      return;
    }
    const cleaned = text.replace(/[^0-9.]/g, '');
    setAreaText(cleaned);
    const value = cleaned === '' ? null : Number(cleaned);
    updateBuilding({
      exclusiveAreaM2: editField(
        building.exclusiveAreaM2,
        value === null || Number.isNaN(value) ? null : value
      ),
    });
  }

  async function handleConfirm() {
    if (!input || !building || building.parking.value === null) {
      return;
    }
    // 확인한 건축물 정보는 화면 표시용으로만 남기고 분석 요청에는 싣지 않는다.
    saveConfirmedBuilding(building);

    if (MOCK_MODE) {
      // mock 모드 — 분석 요청을 보내지 않고 바로 분석 진행 화면으로 간다.
      // 이전 실제 분석 결과가 남아 있으면 리포트가 그걸 보여주므로 지운다.
      clearAnalysisResult();
      clearRequestId();
      router.push('/analysis-progress');
      return;
    }

    setIsSubmitting(true);
    try {
      const fullAddress = input.floorUnit.trim()
        ? `${input.roadAddress} ${input.floorUnit}`
        : input.roadAddress;
      // 분석을 백그라운드로 시작하고(202) 바로 진행 화면으로 간다. 진행 상황과
      // 질문·결과는 진행 화면이 요청 ID로 받아 온다.
      const { request_id: requestId } = await startAnalysis({
        address: fullAddress,
        radiusM: parseRadius(input.radius),
        allowQuestions: true,
      });
      // 이전 분석 결과가 리포트에 섞이지 않게 지우고 새 요청 ID만 남긴다.
      clearAnalysisResult();
      saveRequestId(requestId);
      router.push(`/analysis-progress?id=${encodeURIComponent(requestId)}`);
    } catch (error) {
      console.error('[BuildingConfirmPage] 분석 요청 실패:', error);
      alert(
        error instanceof Error
          ? error.message
          : '분석 요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const floorLabel = floorFromUnit(input?.floorUnit ?? '');

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="mx-auto flex w-full max-w-[1200px] flex-col items-start gap-8 px-4 pt-16 pb-24 sm:px-8">
        {!building ? (
          <>
            <StepIndicator currentStep={2} />
            <BuildingLoading
              statuses={statuses}
              floorLabel={floorLabel}
              address={input?.roadAddress}
            />
          </>
        ) : (
          <>
            <FlowPageTitle
              eyebrow="BUILDING CHECK"
              title="이 정보가 맞나요?"
              description="건축물대장에 적힌 내용이에요. 실제와 다르면 고쳐 주세요. 고친 값으로 분석하고, 리포트에 건축물대장과 다르다고 표시해 둘게요."
            />
            <StepIndicator currentStep={2} />

            {/* 좁은 화면에서는 안내 패널을 확인 카드 아래로 내린다. */}
            <div className="grid w-full grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-10 xl:grid-cols-[minmax(0,1fr)_440px]">
              <Card
                className="w-full gap-0"
                style={{
                  padding: 0,
                  borderRadius: '24px',
                  borderWidth: '0px',
                }}
              >
                <BuildingSummaryHeader building={building} />

                <BuildingFieldRow
                  label="전용면적"
                  field={building.exclusiveAreaM2}
                  format={formatArea}
                  editable={
                    isEditing || building.exclusiveAreaM2.registryValue === null
                  }
                  editor={
                    <div className="flex items-center gap-2">
                      <div className="w-full max-w-48">
                        <Input
                          inputMode="decimal"
                          aria-label="전용면적"
                          value={areaText}
                          onChange={(event) =>
                            handleAreaChange(event.target.value)
                          }
                          placeholder="예: 275.49"
                        />
                      </div>
                      <span
                        className="text-base"
                        style={{ color: colors.text.secondary }}
                      >
                        ㎡
                      </span>
                    </div>
                  }
                />

                <BuildingFieldRow
                  label="주차 가능 여부 (필수)"
                  field={building.parking}
                  format={(value) => PARKING_LABELS[value]}
                  editable={
                    isEditing || building.parking.registryValue === null
                  }
                  editor={
                    <div className="flex flex-col gap-2">
                      <ParkingSelector
                        value={building.parking.value}
                        onChange={(value) =>
                          updateBuilding({
                            parking: editField(building.parking, value),
                          })
                        }
                      />
                      {building.parking.value === null && (
                        <p
                          id="parking-required-hint"
                          className="text-sm leading-relaxed"
                          style={{ color: colors.text.secondary }}
                        >
                          주차 가능 여부를 선택해 주세요. 잘 모르시면 ‘모름’을
                          선택할 수 있어요.
                        </p>
                      )}
                    </div>
                  }
                />

                <BuildingFieldRow
                  label="근린생활시설"
                  field={building.facility}
                  format={(value) => FACILITY_LABELS[value]}
                  editable={
                    isEditing || building.facility.registryValue === null
                  }
                  editor={
                    <SegmentedSelector
                      options={FACILITY_OPTIONS}
                      value={building.facility.value}
                      onChange={(value) =>
                        updateBuilding({
                          facility: editField(building.facility, value),
                        })
                      }
                      ariaLabel="근린생활시설"
                    />
                  }
                />

                <BuildingFieldRow
                  label="오수정화시설"
                  field={building.sewage}
                  format={(value) => value}
                  editable={isEditing || building.sewage.registryValue === null}
                  editor={
                    <select
                      aria-label="오수정화시설"
                      value={building.sewage.value ?? ''}
                      onChange={(event) =>
                        updateBuilding({
                          sewage: editField(
                            building.sewage,
                            (event.target.value ||
                              null) as SewageTreatment | null
                          ),
                        })
                      }
                      className="min-h-[52px] w-full max-w-72 rounded-lg border px-3.5 text-base"
                      style={{
                        borderColor: colors.neutral.border,
                        backgroundColor: colors.neutral.white,
                        color: colors.text.primary,
                      }}
                    >
                      <option value="">선택해 주세요</option>
                      {SEWAGE_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  }
                />

                <div
                  className="flex flex-col-reverse gap-3 px-5 py-6 sm:flex-row sm:justify-end sm:gap-4 sm:px-10 sm:py-8"
                  style={{ borderTop: `1px solid ${colors.neutral.border}` }}
                >
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-[60px] w-full sm:w-auto sm:min-w-[176px]"
                    // Button 기본 text-sm이 클래스보다 우선 적용돼 글자 크기는 style로 준다.
                    style={{
                      fontSize: 'var(--text-base)',
                      color: colors.text.secondary,
                    }}
                    disabled={isSubmitting}
                    aria-pressed={isEditing}
                    onClick={() => setIsEditing((prev) => !prev)}
                  >
                    {isEditing ? '수정 완료' : '고칠게요'}
                  </Button>
                  <Button
                    type="button"
                    variant="primary"
                    className="min-h-[60px] w-full disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                    style={{ fontSize: 'var(--text-base)' }}
                    disabled={isSubmitting || building.parking.value === null}
                    aria-describedby={
                      building.parking.value === null
                        ? 'parking-required-hint'
                        : undefined
                    }
                    onClick={handleConfirm}
                  >
                    {isSubmitting
                      ? '분석을 시작하고 있어요…'
                      : '맞아요 · 이대로 분석하기'}
                  </Button>
                </div>
              </Card>

              <ConfirmSidePanel />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
