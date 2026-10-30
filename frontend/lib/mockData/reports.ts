/**
 * 리포트 목록 목업 — 백엔드에 목록 API가 생기기 전까지 /reports 화면을 채운다.
 * 점수는 리포트의 업종 적합도(확인된 자료 기준 하한)와 같은 0~100 값이다.
 */
export type ReportSummary = {
  id: string;
  address: string;
  floor: string;
  areaPyeong: number;
  analyzedDate: string;
  topIndustry: string;
  score: number;
};

export const mockReports: ReportSummary[] = [
  {
    id: 'mock-hupyeong',
    address: '춘천시 후평동 234-5',
    floor: '2층',
    areaPyeong: 26,
    analyzedDate: '2026.08.22',
    topIndustry: '네일·뷰티',
    score: 92,
  },
  {
    id: 'mock-hyoja',
    address: '춘천시 효자동 181-3',
    floor: '1층',
    areaPyeong: 18,
    analyzedDate: '2026.08.15',
    topIndustry: '무인점포',
    score: 88,
  },
  {
    id: 'mock-soyang',
    address: '춘천시 소양로 45-2',
    floor: '1층',
    areaPyeong: 32,
    analyzedDate: '2026.08.08',
    topIndustry: '소형 카페',
    score: 76,
  },
];
