# 채움 (chum.ai) — Frontend

주소 하나로 유동인구·개폐업·상권 데이터를 분석해 추천/비추천 업종과 근거를 보여주는
AI 공실 분석 서비스의 프론트엔드입니다. Next.js App Router 기반 SPA로,
현재는 `lib/mockData/report.ts`의 목업 데이터로 전체 화면 흐름을 구현해 두었고,
백엔드 에이전트(`../backend`)가 준비되는 대로 실제 API 응답으로 교체합니다.

> 백엔드 진행 상황은 루트 `README.md` 참고. 현재 등록된 분석 API는 없습니다.

## 기술 스택

| 영역 | 선택 |
|---|---|
| 프레임워크 | Next.js 16.3.4 (App Router) |
| 런타임 | React 19.2.8 |
| 언어 | TypeScript |
| 스타일 | Tailwind CSS v4 (CSS-first config, `tailwind.config.js` 없음) |
| 차트 | recharts ^3.10.1 |
| 아이콘 | lucide-react |
| 포맷/린트 | Prettier 3, ESLint 9 (`eslint-config-next` + `eslint-config-prettier`) |

## 시작하기

```bash
npm install
npm run dev
```

[http://localhost:3000](http://localhost:3000) 에서 확인합니다.

```bash
npm run lint     # eslint
npm run format   # prettier --write .
npm run build    # 프로덕션 빌드
```

## 페이지 구성

| 경로 | 파일 | 설명 |
|---|---|---|
| `/` | `app/page.tsx` | 랜딩 페이지 (`Hero`, `StatsRow`, `ProblemCards`, `ValueSteps`, `ReportPreview`, `CTABanner`) |
| `/vacancy-input` | `app/vacancy-input/page.tsx` | 분석할 공실 정보 입력 폼 (`StepIndicator`, `AddressInput`, `AnalysisPreviewPanel`) |
| `/report` | `app/report/page.tsx` | 분석 리포트 (`ReportHeader`, `RecommendationSection`, `AIAnalysisSummary`, `DetailAnalysisTabs`) |

## 디렉터리 구조

```text
frontend/
├─ app/                      # 라우트 (App Router)
├─ components/
│  ├─ layout/                # Header 등 전역 레이아웃
│  ├─ landing/                # 랜딩 페이지 섹션
│  ├─ form/                   # 공실 정보 입력 폼
│  ├─ report/                 # 리포트 상세 탭 (아래 참고)
│  ├─ charts/                 # AreaChart 등 공용 차트 컴포넌트
│  └─ ui/                     # Badge, Button, Card, Tabs 등 범용 UI
├─ lib/mockData/report.ts     # 리포트 전체를 채우는 목업 데이터 (백엔드 연동 전 임시)
├─ styles/tokens.ts           # 색상 등 디자인 토큰
└─ types/                     # 공용 타입 (현재 비어 있음)
```

`components/report/`는 `DetailAnalysisTabs.tsx`가 세 개의 탭으로 묶습니다.

- **유동인구** — `FloatingPopulationSection.tsx`
- **개폐업추이** — `OpenCloseTrendSection.tsx`
- **경쟁업체** — `CompetitorAnalysisSection.tsx`

> 과거 `components/report-v2/`로 분리돼 있던 리포트 컴포넌트들은
> `refactor: report-v2 컴포넌트를 report로 통합, V2 접미사 제거` 커밋에서
> `components/report/`로 합쳐졌습니다. 지금은 v1/v2 구분 없이 이 디렉터리가
> 유일한 구현입니다.

## 디자인/스타일 컨벤션

- **디자인 토큰만 사용** — `styles/tokens.ts`의 `colors.brand.primary`(#00A896),
  `colors.brand.dark`, `colors.status.recommend/notRecommend`,
  `colors.neutral.*`, `colors.accent.orange`를 재사용합니다. 새 hex 값을
  하드코딩하지 않습니다.
- **반응형은 `clamp()` 기반** — Tailwind 반응형 클래스와 같은 CSS 속성을
  같은 요소에 동시에 쓰지 않습니다(캐스케이드 우선순위 충돌 방지). 대신
  `clamp(MINpx, calc(MINpx + (100vw - 기준VWpx) * 기울기), MAXpx)` 형태로
  뷰포트 폭에 비례해 값을 계산합니다.
- **`<style jsx global>`은 렌더링하는 컴포넌트가 직접 소유** — styled-jsx의
  글로벌 스타일 블록은 "그 스타일을 선언한 컴포넌트가 마운트돼 있는가"를
  기준으로 주입/정리됩니다. 다른 탭/페이지에서도 재사용할 스타일이라면,
  최초 사용처가 아니라 실제로 그 클래스를 그리는 공용 컴포넌트(예:
  `AreaChart.tsx`)에 스타일을 둬야 합니다. 그렇지 않으면 그 컴포넌트가
  마운트되지 않은 트리에서는 클래스만 붙고 스타일이 전혀 적용되지 않습니다.
- **opt-in prop으로 하위호환 유지** — 공용 컴포넌트에 새 기능을 추가할 때는
  기본값이 `false`인 boolean prop(예: `AreaChart`의 `showPointLabels`)으로
  넣어, prop을 넘기지 않는 기존 호출부는 이전과 동일하게 렌더링되도록 합니다.

## 목업 데이터

`lib/mockData/report.ts`가 리포트 화면 전체(유동인구/개폐업/경쟁업체/추천 등)를
채우는 단일 목업 소스입니다. 분석 API가 구현되기 전까지는 이 파일을 통해
화면 로직과 반응형 스타일을 검증하고, 실제 연동 시점에는 동일한 타입
인터페이스를 유지한 채 API 응답으로 교체하는 방향을 권장합니다.

## 알려진 정리 대상 (TODO)

- `components/charts/HorizontalBar.tsx`, `VerticalBar.tsx`, `GroupedBar.tsx`는
  현재 어디서도 import되지 않는 미사용 파일입니다(과거 v1 리포트 컴포넌트가
  쓰던 것으로 추정). 정리 필요.
- `app/layout.tsx`의 `metadata`(`title`/`description`)가 `create-next-app`
  기본값(`Create Next App`)에서 아직 변경되지 않았습니다.
