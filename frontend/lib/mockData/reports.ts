import { mockProperty } from '@/lib/mockData/property';

/**
 * 리포트 목록 목업 — 백엔드에 목록 API가 생기기 전까지 /reports 화면을 채운다.
 * 주소·추천 업종·점수는 데모 리포트 화면과 같은 예시 시나리오를 사용한다.
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
    id: 'mock-ogum-404',
    address: mockProperty.address,
    floor: mockProperty.floorUnit,
    areaPyeong: 60.5,
    analyzedDate: '2026.10.30',
    topIndustry: '카페·비알코올 음료점',
    score: 86,
  },
];
