# 채움 — Frontend

| 항목                     | 내용                                                                                         |
| ------------------------ | -------------------------------------------------------------------------------------------- |
| 역할                     | 채움 웹 화면 (주소 입력 · 상가 정보 확인 · 분석 진행 · 리포트 · 계정)                        |
| 운영 주소                | https://chaeum-ai.kr                                                                         |
| 부르는 API               | https://api.chaeum-ai.kr (`NEXT_PUBLIC_API_BASE_URL`)                                        |
| 배포                     | Vercel — develop 커밋을 운영으로 배포, PR마다 미리보기 ([docs/DEPLOY.md](../docs/DEPLOY.md)) |
| API 형태                 | [docs/API_CONTRACT.md](../docs/API_CONTRACT.md)                                              |
| 일부러 둔 예시 화면·표기 | [docs/DESIGN_INTENT.md](../docs/DESIGN_INTENT.md)                                            |

## 기술 스택

| 영역            | 선택                                    |
| --------------- | --------------------------------------- |
| 프레임워크      | Next.js 16.3.4 (App Router)             |
| 화면 라이브러리 | React 19.2.8                            |
| 언어            | TypeScript 5                            |
| 스타일          | Tailwind CSS 4                          |
| 차트            | recharts 3                              |
| 아이콘          | lucide-react                            |
| 시험            | Vitest 4 · Testing Library · Playwright |
| 포맷·린트       | Prettier 3 · ESLint 9                   |
| Node            | 22 (CI 기준)                            |

## 명령

| 명령                                      | 하는 일                                               |
| ----------------------------------------- | ----------------------------------------------------- |
| `npm install`                             | 의존성 설치                                           |
| `npm run dev`                             | 개발 서버 (http://localhost:3000)                     |
| `npm run build` · `npm run start`         | 운영용 빌드 · 실행                                    |
| `npm test`                                | 단위·화면 시험 (Vitest)                               |
| `npm run test:coverage`                   | 같은 시험 + 줄 커버리지 하한 55% 확인 (CI가 돌림)     |
| `npm run e2e`                             | E2E 시험 (Playwright, 백엔드 8123 · 화면 3123에 띄움) |
| `npm run lint`                            | ESLint                                                |
| `npm run typecheck`                       | 타입 검사                                             |
| `npm run format:check` · `npm run format` | Prettier 검사 · 정리                                  |

## 환경 변수

| 이름                            | 쓰임                                       | 비워 두면                                   |
| ------------------------------- | ------------------------------------------ | ------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL`      | 백엔드 주소                                | `http://127.0.0.1:8000`                     |
| `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | 리포트 지도(카카오맵)                      | 간단한 지도 그림 + "카카오맵에서 보기" 링크 |
| `NEXT_PUBLIC_MOCK_MODE`         | `true`면 백엔드 없이 목업 자료로 전체 흐름 | 실제 백엔드 호출                            |
| `E2E_PYTHON`                    | E2E 시험이 백엔드를 띄울 파이썬 경로       | `python`                                    |

## 화면

| 경로                                   | 파일                                         | 화면                                  | 로그인                         |
| -------------------------------------- | -------------------------------------------- | ------------------------------------- | ------------------------------ |
| `/`                                    | `app/page.tsx`                               | 첫 화면                               | 필요 없음                      |
| `/signup`                              | `app/signup/page.tsx`                        | 회원가입                              | 필요 없음                      |
| `/login`                               | `app/login/page.tsx`                         | 로그인 (메일 · 카카오)                | 필요 없음                      |
| `/verify-email`                        | `app/verify-email/page.tsx`                  | 메일 인증                             | 필요 없음                      |
| `/password/forgot` · `/password/reset` | `app/password/`                              | 비밀번호 재설정                       | 필요 없음                      |
| `/vacancy-input`                       | `app/(protected)/vacancy-input/page.tsx`     | 주소 · 층 입력                        | 필요                           |
| `/building-confirm`                    | `app/(protected)/building-confirm/page.tsx`  | 건축물대장 값 확인 · 빈칸 입력        | 필요                           |
| `/analysis-progress`                   | `app/(protected)/analysis-progress/page.tsx` | 분석 진행 · 질문 답변                 | 필요                           |
| `/report`                              | `app/report/page.tsx`                        | 리포트                                | 필요 (예시 리포트는 없이 열림) |
| `/my/reports`                          | `app/my/reports/page.tsx`                    | 내 분석 기록                          | 필요                           |
| `/reports`                             | `app/reports/page.tsx`                       | 예시 리포트 목록                      | 필요 없음                      |
| `/prototypes/tenant-search`            | `app/prototypes/tenant-search/page.tsx`      | 임차인용 매물 탐색 시제품 (예시 매물) | 필요 없음                      |

## 폴더

| 경로               | 내용                                                                                                                       |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `app/`             | 화면 (라우트)                                                                                                              |
| `components/`      | 화면 조각 — `landing` · `form` · `building-confirm` · `analysis-progress` · `report` · `auth` · `layout` · `charts` · `ui` |
| `lib/api/`         | 백엔드 호출 · 응답 변환                                                                                                    |
| `lib/hooks/`       | 진행 상황 조회 등 화면 훅                                                                                                  |
| `lib/mockData/`    | 목업 모드 · 예시 리포트 자료                                                                                               |
| `styles/tokens.ts` | 디자인 토큰                                                                                                                |
| `e2e/`             | Playwright 시나리오                                                                                                        |
| `public/`          | 이미지                                                                                                                     |

## 시험

| 종류      | 실행                                              | 위치                       |
| --------- | ------------------------------------------------- | -------------------------- |
| 단위·화면 | `npm test`                                        | 각 파일 옆 `*.test.ts(x)`  |
| E2E       | `E2E_PYTHON=<백엔드 가상환경 파이썬> npm run e2e` | `e2e/*.e2e.ts`             |
| CI        | 형식 검사 · 린트 · 시험 · 빌드 · E2E              | `.github/workflows/ci.yml` |
