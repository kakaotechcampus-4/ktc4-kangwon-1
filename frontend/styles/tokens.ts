export const colors = {
  brand: {
    primary: '#00A896',
    dark: '#004F54',
  },
  status: {
    recommend: '#00A896',
    notRecommend: '#FF5A5F',
  },
  neutral: {
    white: '#FFFFFF',
    background: '#F8F9FA',
    border: '#E2E6E8',
    black: '#000000',
  },
  accent: {
    orange: '#FC881D',
  },
  // 카카오 공식 버튼 규격 색이라 바꿀 수 없다. 토큰으로 올려 두고 그것만 쓴다.
  kakao: {
    yellow: '#FEE500',
    label: '#191600',
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
