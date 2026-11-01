/**
 * 랜딩 "사장님들의 이야기" 목업 후기.
 * 실제 사용자 후기가 아니라 화면 구성을 보기 위한 예시 문장이다.
 * 실제 후기를 받으면(작성자 동의 필수) 이 파일을 교체하고, 그 전까지는 화면에
 * "예시 후기" 안내를 함께 둔다(components/landing/Testimonials.tsx).
 */
export type Testimonial = {
  id: string;
  author: string; // "지역 · 상가 정보"
  rating: 1 | 2 | 3 | 4 | 5;
  body: string;
};

export const mockTestimonials: Testimonial[] = [
  {
    id: 'songpa-2f',
    author: '서울 송파 · 2층 상가 건물주',
    rating: 5,
    body: '공실이 반년째라 막막했는데, 2층에 맞는 업종부터 추려 줘서 중개사님이랑 이야기하기가 훨씬 수월했어요.',
  },
  {
    id: 'chuncheon-1f',
    author: '춘천 · 1층 상가 임대인',
    rating: 5,
    body: '전 임차인이랑 같은 업종을 또 들일 뻔했는데, 주변에 같은 가게가 몇 곳인지 보고 생각을 바꿨습니다.',
  },
  {
    id: 'daegu-new',
    author: '대구 · 신축 상가 건물주',
    rating: 5,
    body: '동네를 잘 몰라서 걱정이었는데 시간대별 유동인구를 보니 어떤 가게가 어울릴지 감이 왔어요.',
  },
  {
    id: 'gangdong-3',
    author: '서울 강동 · 상가 3곳 보유',
    rating: 5,
    body: '추천 이유랑 자료 출처가 같이 나와서, 임차 희망자분께 왜 이 업종인지 설명하기 좋았습니다.',
  },
  {
    id: 'incheon-school',
    author: '인천 · 학교 앞 상가 임대인',
    rating: 5,
    body: '학교 근처라 규제가 제일 걱정이었는데, 들이면 안 되는 업종을 미리 표시해 줘서 안심됐어요.',
  },
];
