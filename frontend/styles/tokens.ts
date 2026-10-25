// 브랜드 색 — 파랑(primary)과 남색(dark). 2026-10 리디자인에서 초록 계열을 대체했다.
export const colors = {
  brand: {
    primary: '#2453D6',
    dark: '#10233A',
    // 히어로·카드 바탕에 쓰는 아주 연한 하늘색
    wash: '#EAF2F7',
  },
  status: {
    recommend: '#2453D6',
    notRecommend: '#D9542E',
  },
  neutral: {
    white: '#FFFFFF',
    background: '#F5F8FB',
    border: '#E2E8EE',
    black: '#000000',
  },
  accent: {
    // 이름은 하위호환을 위해 그대로 두고 값만 리디자인 톤의 진한 앰버로 바꿨다.
    orange: '#D98A12',
  },
  // 글자 색 단계 — 읽어야 하는 글은 secondary까지만 쓰고, placeholder는
  // 입력 안내나 중요도가 아주 낮은 정보에만 쓴다.
  text: {
    primary: '#111827',
    secondary: '#4B5563',
    tertiary: '#6B7280',
    placeholder: '#9CA3AF',
  },
} as const;
