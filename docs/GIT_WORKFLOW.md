# Git 워크플로

## 브랜치

```
main      멘토 리뷰를 받은 결과물. 여기로는 develop만 들어온다
develop   기본 브랜치. 팀의 현재 상태
feature/* 기능 작업.  feature/commercial-area-async
fix/*     버그 수정
refactor/* 리뷰 반영·정리
docs/*    문서만 바뀔 때
```

**작업 브랜치는 develop에서 따고 develop으로 돌아옵니다.** `main`에 직접 push하지 않습니다.

```bash
git switch develop && git pull
git switch -c feature/무엇을-하는지
```

## 커밋

`type: 무엇을 했는지` 한 줄. 한국어로 씁니다.

| type | 쓸 때 |
| --- | --- |
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작은 그대로, 구조만 바꿈 |
| `docs` | 문서 |
| `test` | 시험 추가·수정 |
| `chore` | 설정·의존성 |

```
feat: 상권 에이전트 비동기 전환과 페이지 병렬 조회
fix: 자치구 코드가 없을 때 분석이 멈추던 문제
docs: 백엔드 README에 데이터 흐름 추가
```

**한 커밋은 한 가지만 합니다.** 포맷 정리와 기능 추가를 같은 커밋에 섞지 않습니다.
리뷰어가 "이건 왜 바뀌었지"를 묻지 않아도 되게 만드는 것이 목적입니다.

## PR

### 팀 내부 PR — `feature/* → develop`

- **모든 작업은 PR로 들어옵니다.** develop에 직접 push하지 않습니다.
- 리뷰어를 한 명 지정합니다. 같은 파트가 아니어도 됩니다.
- 리뷰의 목적은 결함 찾기보다 **서로 무엇을 만들고 있는지 아는 것**입니다.
  꼼꼼히 볼 시간이 없으면 "무엇이 어떻게 바뀌었는지 이해했다"만 확인하고 승인해도 됩니다.
- 리뷰가 하루 넘게 막히면 그냥 머지합니다. **리뷰가 병목이 되면 리뷰를 안 하는 것보다 나쁩니다.**
- CI(`ci.yml`)가 통과해야 머지합니다.

### 멘토 리뷰 PR — `develop → main`

- 주 1회, 리뷰받고 싶은 상태에서 올립니다.
- **base가 `main`인지 확인합니다.** GitHub이 `develop`을 기본으로 채워 두는데,
  `main`이 아니면 멘토가 자동 지정되지 않습니다.
- PR 템플릿의 **"리뷰에서 봐주셨으면 하는 곳"** 을 반드시 채웁니다.
  "전체 봐주세요"보다 "이 방식이 맞는지 모르겠습니다"가 훨씬 나은 리뷰를 받습니다.
- 질문은 **2~3개로 좁힙니다.** 7개를 한 번에 물으면 답을 받기 어렵습니다.
- 지난 리뷰를 반영했다면 "지난 리뷰 반영"에 어디를 어떻게 고쳤는지 적습니다.
  반영하지 않기로 한 것이 있으면 그 이유도 적습니다.

## 충돌이 났을 때

```bash
git switch develop && git pull
git switch feature/내-브랜치
git merge develop        # rebase 대신 merge를 씁니다. 이력이 남는 편이 추적하기 쉽습니다
```

`package-lock.json`이 충돌하면 develop 쪽을 받고 `npm install`을 다시 돌립니다.

## 리뷰 자동화 — 건드리지 않기

`.github/workflows/assign-mentor.yml` · `notify-discord.yml` · `convention-check.yml` · `.github/CODEOWNERS`
운영진 소유입니다. 팀 CI(`ci.yml`)를 포함해 **새 워크플로를 추가하는 것은 자유**지만
위 4개는 고치지 않습니다.
