/**
 * "분석 진행" 화면(공실 입력 → 분석 진행 → 리포트의 2단계)이 쓰는 타입과
 * 목업 데이터. 실제 API 계약이 아직 확정되지 않아 mockReportData(report.ts)와
 * 같은 패턴으로 분리해뒀다 — 나중에 실제 응답으로 교체할 때는 이 파일의
 * 타입을 backend/app/schemas.py 기준으로 맞추고, 값은 실제 API 어댑터가
 * 채우도록 바꾸면 된다. 컴포넌트는 이 타입에만 의존한다.
 *
 * 아래 phases의 status 값은 화면 모양을 참고하기 위한 기본값일 뿐이다 —
 * 실제 진행 시뮬레이션은 lib/hooks/useAnalysisProgressSimulation.ts가
 * 마운트 시 전부 pending으로 리셋하고 스스로 진행시키므로, 여기 값을
 * 바꿔도 화면에 영향이 없다. 각 항목이 얼마나 걸리는지(병렬 진행 속도,
 * phase별 소요 시간)를 바꾸려면 그 훅의 SUB_STEP_DURATIONS_MS /
 * PHASE_DURATIONS_MS를 수정한다.
 */

export type ProgressStepStatus = 'pending' | 'in_progress' | 'done';

export type ProgressStep = {
  id: string;
  label: string;
  description: string;
  status: ProgressStepStatus;
};

export type ProgressPhase = {
  id: string;
  title: string;
  description: string;
  status: ProgressStepStatus;
  subSteps?: ProgressStep[];
};

export type ClarifyingQuestion = {
  questionId: string;
  question: string;
  context: string;
  options: string[];
  askedAt: string; // 표시용 시간 문자열
};

export type AnalysisSummary = {
  address: string;
  floorAndUnit: string;
  radiusM: number;
  exclusiveAreaText: string; // "26평 (약 85.9㎡)"
  centerLat: number;
  centerLng: number;
  nearbyLandmarks: { name: string; lat: number; lng: number }[];
};

export const mockAnalysisProgress = {
  phases: [
    {
      id: 'data-collection',
      title: '데이터 수집 중',
      description: '입력하신 주소를 기반으로 주변 데이터를 수집하고 있어요.',
      status: 'pending',
      subSteps: [
        {
          id: 'basic-info',
          label: '기본 정보 확인',
          description: '건물 정보, 용도, 면적 등',
          status: 'pending',
        },
        {
          id: 'commercial-area',
          label: '주변 상권 데이터',
          description: '반경 500m 내 경쟁업체, 업종 분포',
          status: 'pending',
        },
        {
          id: 'floating-population',
          label: '유동인구 데이터',
          description: '시간대별, 요일별 유동인구',
          status: 'pending',
        },
        {
          id: 'business-lifecycle',
          label: '개폐업 데이터',
          description: '최근 3년 개폐업 현황',
          status: 'pending',
        },
      ],
    },
    {
      id: 'ai-analysis',
      title: 'AI 분석 진행 중',
      description: '수집한 데이터를 종합하여 업종 적합도를 분석하고 있어요.',
      status: 'pending',
    },
    {
      id: 'result-compilation',
      title: '결과 정리 중',
      description: '분석 결과를 정리하고 맞춤 리포트를 생성하고 있어요.',
      status: 'pending',
    },
  ] as ProgressPhase[],

  questions: [
    {
      questionId: 'interior-work',
      question: '이 공간에는 별도의 인테리어 공사가 가능한가요?',
      context: '네일·뷰티 업종은 수도, 전기, 배수 시설이 필요할 수 있어요.',
      options: ['네, 가능합니다', '제한이 있어요', '모르겠어요'],
      askedAt: '오후 2:14',
    },
    {
      questionId: 'parking',
      question: '현재 주차 이용이 가능한가요?',
      context: '주차 가능 여부에 따라 추천 업종이 달라질 수 있어요.',
      options: ['가능해요', '불가능해요', '모르겠어요'],
      askedAt: '오후 2:14',
    },
  ] as ClarifyingQuestion[],

  summary: {
    address: '서울특별시 관악구 봉천로 123',
    floorAndUnit: '1층 101호',
    radiusM: 500,
    exclusiveAreaText: '26평 (약 85.9㎡)',
    // 목업 좌표 — 실제 지도 연동 전까지는 화면에 직접 쓰이지 않는다.
    // TODO: 실제 지도(카카오맵/네이버맵 등) 연동 시 이 좌표와
    // nearbyLandmarks[].lat/lng를 그대로 마커 배치에 사용한다.
    centerLat: 37.4784,
    centerLng: 126.9516,
    nearbyLandmarks: [
      { name: '서울대입구역', lat: 37.4812, lng: 126.9526 },
      { name: '봉천역', lat: 37.4826, lng: 126.9574 },
    ],
  } as AnalysisSummary,
};
