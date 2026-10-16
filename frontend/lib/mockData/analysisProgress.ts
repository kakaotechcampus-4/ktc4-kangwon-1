import { mockProperty } from '@/lib/mockData/property';
/**
 * "분석 진행" 화면(공실 입력 → 분석 진행 → 리포트의 2단계)이 쓰는 타입과
 * 목업 데이터. 실제 API 계약이 아직 확정되지 않아 mockReportData(report.ts)와
 * 같은 패턴으로 분리해뒀다 — 나중에 실제 응답으로 교체할 때는 이 파일의
 * 타입을 backend/app/schemas.py 기준으로 맞추고, 값은 실제 API 어댑터가
 * 채우도록 바꾸면 된다. 컴포넌트는 이 타입에만 의존한다.
 *
 * 화면이 보여주는 흐름은 "분석 중 → 정보 부족 → 사용자 답변 대기 → 답변 후
 * 분석 재개"다. 아래 steps의 status 값은 화면 모양을 참고하기 위한 기본값일
 * 뿐이다 — 실제 진행 시뮬레이션은 lib/hooks/useAnalysisProgressSimulation.ts가
 * 마운트 시 전부 pending으로 리셋하고 스스로 진행시킨다.
 *
 * 단계 라벨은 사용자(임대인)가 읽는 문장이다. 백엔드 내부 용어(에이전트,
 * 노드, 그래프 등)는 여기에 쓰지 않는다.
 */

// waiting = 사용자 답변이 있어야 넘어갈 수 있는 단계(분석 일시정지).
export type ProgressStepStatus = 'pending' | 'in_progress' | 'waiting' | 'done';

export type ProgressStep = {
  id: string;
  label: string;
  description: string;
  status: ProgressStepStatus;
};

// 화면 전체의 현재 상태 — 헤더 문구와 중앙 영역 모양이 이 값으로 갈린다.
export type AnalysisStage =
  | 'analyzing' // 추가 질문이 생기기 전까지 분석 중
  | 'awaiting_input' // 정보가 부족해 사용자 답변을 기다리는 중
  | 'resuming' // 답변을 받아 최종 판단을 이어가는 중
  | 'completed'
  | 'failed'; // 분석 실패(실제 백엔드 연결 시)

export type ClarifyingOption = {
  id: string;
  label: string;
  detailInput?: {
    label: string;
    placeholder?: string;
    required: boolean;
  };
};

export type ClarifyingAnswer = {
  optionId: string;
  detail?: string;
};

export type ClarifyingAnswers = Record<string, ClarifyingAnswer>;

export type ClarifyingQuestion = {
  questionId: string;
  question: string;
  // 답변 반영 요약에 쓰는 짧은 이름 — "인테리어 공사", "주차"
  shortLabel: string;
  // 질문 바로 아래 한 줄 안내
  context: string;
  // "왜 필요한가요?"를 펼쳤을 때 — 이 답이 분석 결과에 어떻게 쓰이는지
  reason: string;
  options: ClarifyingOption[];
};

export type AnalysisSummary = {
  address: string;
  floorAndUnit: string;
  radiusM: number;
  exclusiveAreaText: string; // "275.49㎡ (약 83.3평)"
  centerLat: number;
  centerLng: number;
};

export const mockAnalysisProgress = {
  // 단계 id는 lib/api/adapters/progress.ts STEP과 같다(백엔드 진행 이벤트 순서).
  steps: [
    {
      id: 'address',
      label: '주소 확인',
      description: '입력한 주소의 위치와 분석 반경 확인',
      status: 'pending',
    },
    {
      id: 'local-data',
      label: '주변 자료 조회·채점',
      description: '상권·유동인구·개폐업 자료로 51개 업종 점수 계산',
      status: 'pending',
    },
    {
      id: 'decision',
      label: '업종 판단',
      description: 'AI가 근거를 확인하며 업종별 적합도 판단',
      status: 'pending',
    },
    {
      id: 'clarification',
      label: '추가 정보 확인',
      description: '업종 판단에 필요한 공간 조건 확인',
      status: 'pending',
    },
    {
      id: 'evaluation',
      label: '평가자 검토',
      description: '심사위원·창업자·고객·임대인 관점 4명이 판단 검토',
      status: 'pending',
    },
    {
      id: 'report',
      label: '최종 리포트 작성',
      description: '검토 의견을 반영해 추천 업종과 확인 조건 정리',
      status: 'pending',
    },
  ] as ProgressStep[],

  questions: [
    {
      questionId: 'interior-work',
      question: '이 공간에 별도 인테리어 공사가 가능한가요?',
      shortLabel: '인테리어 공사',
      context: '수도·전기·배수 공사가 가능한지 알려주세요.',
      reason:
        '네일·뷰티, 카페, 음식점처럼 수도·배수·전기 증설이 필요한 업종을 추천 후보에 넣을지 판단하는 데 쓰여요. 공사에 제한이 있다면 설비 공사가 적게 드는 업종 위주로 추천합니다.',
      options: [
        { id: 'available', label: '네, 가능합니다' },
        {
          id: 'restricted',
          label: '제한이 있어요',
          detailInput: {
            label: '어떤 제한사항이 있나요?',
            placeholder: '예: 배수 공사는 어렵고, 전기 증설은 가능해요',
            required: true,
          },
        },
        { id: 'unknown', label: '모르겠어요' },
      ],
    },
    {
      questionId: 'parking',
      question: '건물에서 주차를 이용할 수 있나요?',
      shortLabel: '주차',
      context: '방문 고객이 차를 세울 수 있는지 알려주세요.',
      reason:
        '주차 가능 여부는 병원, 학원, 자동차 관련 업종처럼 차량 접근성이 중요한 업종의 적합도 판단에 사용됩니다. 주차가 어렵다면 도보 유동인구 비중이 높은 업종의 점수를 더 높게 봅니다.',
      options: [
        { id: 'available', label: '가능해요' },
        { id: 'unavailable', label: '불가능해요' },
        { id: 'unknown', label: '모르겠어요' },
      ],
    },
  ] as ClarifyingQuestion[],

  summary: {
    address: mockProperty.address,
    floorAndUnit: mockProperty.floorUnit,
    radiusM: mockProperty.radiusM,
    exclusiveAreaText: mockProperty.exclusiveAreaText,
    // 목업 좌표 — 실제 지도 연동 전까지는 화면에 직접 쓰이지 않는다.
    // TODO: 실제 지도(카카오맵/네이버맵 등) 연동 시 이 좌표를 마커 배치에 쓴다.
    centerLat: mockProperty.latitude,
    centerLng: mockProperty.longitude,
  } as AnalysisSummary,
};
