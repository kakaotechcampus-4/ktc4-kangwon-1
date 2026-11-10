# 의도한 동작

오류처럼 보일 수 있지만 일부러 이렇게 만든 부분입니다.

| 화면·표기 | 지금 동작 | 이렇게 둔 이유 | 위치 |
| --- | --- | --- | --- |
| 리포트의 임차인 찾기(중개사 연결) | 예시 중개사 목록에서 최대 3곳을 고르면 "중개사에게 매물 등록을 요청했어요"가 나옵니다. 서버로 보내는 요청은 없습니다. 고르는 화면에 "화면 확인용 예시 중개사예요. 실제 중개사 연결은 준비 중이에요." 안내가 있습니다. | 지금은 프로젝트 단계라 실제 공인중개사와 계약하고 연결할 수 없습니다. 연결이 생겼을 때의 흐름을 보여 주려고 화면(FE)까지만 만들었습니다. | `frontend/components/report/TenantMatchingProposal.tsx` |
| 임대인–임차인 매칭 | 매칭은 화면까지만 있고 서버 기능은 없습니다. 임차인용 매물 탐색 시제품 화면도 예시 매물로만 동작합니다. | 같은 이유입니다. 실제 임차인·매물 자료와 중개 연결이 없어 지금은 구현할 수 없습니다. 서비스가 이어질 방향을 보여 주는 화면입니다. | `frontend/app/prototypes/tenant-search/` |
| chum.ai 표기 | 첫 화면 로고는 CHAIUM에서 AI가 빠져나가 CHUM.AI가 되는 움직이는 로고입니다. 머리글·바닥글의 chum.ai는 이 로고의 이름입니다. 운영 주소는 chaeum-ai.kr입니다. | "빈 자리를 AI로 채운다"는 뜻을 담은 브랜드 표기입니다. 오타가 아니므로 바꾸지 않습니다. | `frontend/components/landing/Hero.tsx`, `frontend/app/globals.css`(`.wordmark`), `frontend/components/layout/Header.tsx`, `frontend/components/layout/Footer.tsx` |
| 주소 입력은 로그인 뒤 | 주소 입력·상가 정보 확인·분석 진행 화면은 로그인해야 열리고, 분석 시작은 메일 인증을 마친 계정만 할 수 있습니다. 서울 밖 주소는 상가 정보 확인 화면에서 "채움은 지금 서울에 있는 상가만 분석해요."로 안내합니다. | 주소·층·면적·설비처럼 임대인의 상가 정보를 받아 저장하고, 결과는 그 계정에만 보여 줍니다(다른 사람의 분석은 404). 건축물대장 조회는 외부 API 할당량을 쓰므로 로그인한 사람만 부를 수 있게 했습니다. | `frontend/app/(protected)/`, `backend/app/api/v1/building.py`, `backend/app/api/v1/analyses.py` |
