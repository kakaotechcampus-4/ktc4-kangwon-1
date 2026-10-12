import type { ClarifyingQuestion } from './analysisProgress';

// 개발 환경에서 공통 질문 UI를 확인하기 위한 대체 질문이다.
export const demoClarifyingQuestions: ClarifyingQuestion[] = [
  {
    questionId: 'new-ventilation-question',
    question: '환기 설비는 어떤 상태인가요?',
    shortLabel: '환기 설비',
    context: '현재 설비 상태를 알려주세요.',
    reason: '설비 조건을 확인해요.',
    options: [
      { id: 'ready', label: '설치되어 있어요' },
      { id: 'install', label: '새로 설치해야 해요' },
      {
        id: 'approval',
        label: '건물주 협의가 필요해요',
        detailInput: {
          label: '협의할 내용을 적어주세요',
          placeholder: '예: 외벽 타공 허가 필요',
          required: true,
        },
      },
      { id: 'unsure', label: '확인하지 못했어요' },
    ],
  },
  {
    questionId: 'new-sign-question',
    question: '간판을 설치할 수 있나요?',
    shortLabel: '간판',
    context: '간판 설치 조건을 알려주세요.',
    reason: '노출 조건을 확인해요.',
    options: [
      { id: 'yes', label: '설치할 수 있어요' },
      {
        id: 'conditional',
        label: '조건이 있어요',
        detailInput: { label: '간판 조건', required: false },
      },
    ],
  },
];
