# 프론트엔드

임대인이 공실 주소를 넣고 **업종 추천 리포트**를 받아 보는 화면입니다.

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4.

## 실행

```bash
cd frontend
npm install
npm run dev
```

<http://localhost:3000>

백엔드를 함께 띄우려면 다른 터미널에서:

```bash
cd backend
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --reload
```

**백엔드 키가 없어도 됩니다.** `MOCK_MODE=1`이면 실제와 같은 형태의 고정 응답이 옵니다.
주고받는 형태는 [../docs/API_CONTRACT.md](../docs/API_CONTRACT.md)에 있습니다.

## 화면 구조

| 경로             | 파일                         | 내용                                                                          |
| ---------------- | ---------------------------- | ----------------------------------------------------------------------------- |
| `/`              | `app/page.tsx`               | 랜딩. Hero → StatsRow → ProblemCards → ValueSteps → ReportPreview → CTABanner |
| `/vacancy-input` | `app/vacancy-input/page.tsx` | 공실 정보 입력 (주소 · 상세주소)                                              |

```
app/                 라우트
components/
  ui/                Button · Input · Card · Badge · ProgressBar
  layout/            Header
  landing/           랜딩 전용 섹션
  form/              입력 화면 전용
lib/                 API 호출·유틸 (예정)
types/               백엔드 계약을 옮긴 타입 (예정)
styles/tokens.ts     색 토큰 — 헥사값을 컴포넌트에 직접 쓰지 않는다
```

## 아직 안 된 것

- **백엔드 연동이 없습니다.** `fetch` 호출이 아직 한 곳도 없습니다. `lib/`에 API 함수를 만들고
  `/vacancy-input`의 제출을 `POST /api/v1/analyses`에 붙이는 것이 다음 작업입니다.
- 결과 화면(리포트)이 없습니다. 지금은 랜딩의 `ReportPreview`가 정적 예시입니다.

## 반응형 규칙

- 컨테이너에 **고정 px 폭을 쓰지 않습니다.** `w-[1440px]`이 아니라 `w-full max-w-[1440px]`입니다.
  고정폭은 그보다 좁은 화면에서 가로 스크롤을 만듭니다.
- 나열은 `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3`을 씁니다.
- 브레이크포인트는 Tailwind 기본값(`sm 640 · md 768 · lg 1024 · xl 1280`)입니다.
- 디자인이 절대좌표로 잡혀 있으면 비율(%)과 컨테이너 단위(`cqw`)로 옮깁니다.
  `components/landing/Hero.tsx`의 `pctX` · `fs` 헬퍼가 그 방식입니다.

## 검사

```bash
npm run format:check   # prettier
npm run lint           # eslint
npm run build          # 타입 검사 포함
```

`npm run typecheck`(`tsc --noEmit`)는 Next가 만든 타입이 있어야 하므로 **`npm run build`를 한 번 돌린 뒤** 씁니다.

CI(`../.github/workflows/ci.yml`)가 PR마다 위 세 가지를 돌립니다.

## 규칙 문서

- 코드 컨벤션: [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md)
- Git 워크플로: [../docs/GIT_WORKFLOW.md](../docs/GIT_WORKFLOW.md)
- API 계약: [../docs/API_CONTRACT.md](../docs/API_CONTRACT.md)
