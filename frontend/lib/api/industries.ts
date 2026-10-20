/**
 * 서비스 51개 업종 이름표. backend/app/industries/data/industries.csv에서 옮겼다.
 * 백엔드 카탈로그 버전 e5a4d86a0282. 업종이 바뀌면 같이 고친다.
 * top5에는 industry_name이 오지만 facts·L_records에는 코드만 와서 화면 이름에 쓴다.
 */
export const INDUSTRIES: Record<string, { name: string; major: string }> = {
  G202: { name: '자동차부품 소매', major: '소매업' },
  G203: { name: '모터사이클·운동용품·자전거 소매', major: '소매업' },
  G204: { name: '종합 소매', major: '소매업' },
  G205: { name: '식료품 소매', major: '소매업' },
  G208: { name: '가전·정보통신장비 소매', major: '소매업' },
  G209: { name: '의류·신발·가방·섬유 소매', major: '소매업' },
  G210: { name: '철물·건설자재·생활용품 소매', major: '소매업' },
  G211: { name: '가구 소매', major: '소매업' },
  G213: { name: '문화·오락·여가용품 소매', major: '소매업' },
  G215: { name: '의약품·의료기기 소매', major: '소매업' },
  G215B: { name: '화장품 소매', major: '소매업' },
  G216: { name: '안경·정밀기기 소매', major: '소매업' },
  G217: { name: '시계·귀금속 소매', major: '소매업' },
  G218: { name: '예술품·기념품 소매', major: '소매업' },
  G219: { name: '화초·식물 소매', major: '소매업' },
  G220: { name: '애완동물·관련용품 소매', major: '소매업' },
  G222: { name: '중고 상품 소매', major: '소매업' },
  I101: { name: '일반·생활 숙박', major: '숙박업' },
  I102: { name: '기타 숙박', major: '숙박업' },
  I201: { name: '한식 음식점', major: '음식점업' },
  I202: { name: '중식 음식점', major: '음식점업' },
  I203: { name: '일식 음식점', major: '음식점업' },
  I204: { name: '양식·외국식 음식점', major: '음식점업' },
  I207: { name: '구내식당 및 뷔페', major: '음식점업' },
  I210: { name: '간이 음식점', major: '음식점업' },
  I211: { name: '주점', major: '음식점업' },
  I212: { name: '카페·비알코올 음료점', major: '음식점업' },
  L102: { name: '부동산 관련 서비스', major: '부동산업' },
  M103: { name: '법무 서비스', major: '전문, 과학 및 기술 서비스업' },
  M104: { name: '회계·세무 서비스', major: '전문, 과학 및 기술 서비스업' },
  M107: {
    name: '회사 본부·경영 컨설팅 서비스',
    major: '전문, 과학 및 기술 서비스업',
  },
  M111: { name: '수의업', major: '전문, 과학 및 기술 서비스업' },
  M113: { name: '사진 촬영·처리', major: '전문, 과학 및 기술 서비스업' },
  M114: { name: '인쇄 및 제품 제작', major: '전문, 과학 및 기술 서비스업' },
  N102: {
    name: '건물 청소·방제',
    major: '사업시설 관리, 사업 지원 및 임대 서비스업',
  },
  N105: {
    name: '여행 서비스',
    major: '사업시설 관리, 사업 지원 및 임대 서비스업',
  },
  N109: {
    name: '운송장비 대여',
    major: '사업시설 관리, 사업 지원 및 임대 서비스업',
  },
  N110: {
    name: '개인·가정용품 대여',
    major: '사업시설 관리, 사업 지원 및 임대 서비스업',
  },
  P105: { name: '학원·교육기관', major: '교육 서비스업' },
  Q102: { name: '의원', major: '보건의료업' },
  R102: {
    name: '독서실·유사 여가시설',
    major: '예술, 스포츠 및 여가관련 서비스업',
  },
  R103: { name: '스포츠 서비스', major: '예술, 스포츠 및 여가관련 서비스업' },
  R104: { name: '오락 서비스', major: '예술, 스포츠 및 여가관련 서비스업' },
  S201: { name: '컴퓨터 및 주변기기 수리', major: '수리 및 개인 서비스업' },
  S202: { name: '통신장비 수리', major: '수리 및 개인 서비스업' },
  S203: { name: '자동차 수리·세차', major: '수리 및 개인 서비스업' },
  S204: { name: '모터사이클 수리', major: '수리 및 개인 서비스업' },
  S205: { name: '가전제품 수리', major: '수리 및 개인 서비스업' },
  S207: { name: '이용·미용', major: '수리 및 개인 서비스업' },
  S208: { name: '욕탕·마사지·신체관리 서비스', major: '수리 및 개인 서비스업' },
  S209: { name: '세탁', major: '수리 및 개인 서비스업' },
};

export function industryName(code: string): string {
  return INDUSTRIES[code]?.name ?? code;
}
