# 배포·운영

지금 운영 중인 구조와 절차입니다. 2026-11-08 기준(develop `b936689`).

## 한눈에

| 무엇 | 주소 | 배포 |
| --- | --- | --- |
| 서비스 화면 | https://chaeum-ai.kr | Vercel이 develop 커밋을 운영으로 배포합니다. `ktc4-kangwon-1.vercel.app`은 chaeum-ai.kr로 넘어갑니다(`frontend/next.config.ts`) |
| API | `https://api.chaeum-ai.kr` (화면이 부르는 주소 — 맨 앞 주소는 페이지가 없어 Not Found가 정상) | GitHub Actions `deploy.yml` → AWS EC2 한 대, 무중단 전환 |
| API 문서 | https://api.chaeum-ai.kr/docs · `/openapi.json` | FastAPI가 코드에서 만듭니다 |
| 상태 확인 | https://api.chaeum-ai.kr/health | `{"status":"ok"}` |

`kangwon-1-chaeum.duckdns.org`는 같은 서버의 다른 주소입니다. 배포 워크플로의 마지막 외부 확인이 이 주소를 씁니다.

백엔드 배포 워크플로는 2026-10-10부터 39번 실행해 39번 모두 성공했습니다(2026-11-08 기준, Actions 탭 「배포」).

## 환경

| 환경 | 어디서 | 자료·AI | 쓰는 때 |
| --- | --- | --- | --- |
| 로컬 | 개발자 PC — 백엔드 `uvicorn`, 프론트 `npm run dev` | 각자 `backend/.env`, 로컬 SQLite, 실제 LLM 키 | 개발 |
| 화면 mock 모드 | 로컬 프론트, `NEXT_PUBLIC_MOCK_MODE=true` | 백엔드 없이 고정 데이터 | 화면 흐름 확인 |
| CI | GitHub Actions `ci.yml` — 모든 PR, main·develop push | 백엔드 검사·시험, 프론트 검사·빌드, 브라우저 E2E(백엔드 `MOCK_MODE=1`, 실제 AI 호출 없음) | 머지 전 검사 |
| PR 미리보기 | Vercel Preview — PR마다 미리보기 주소를 PR 댓글로 남김 | 화면 | 리뷰 |
| 운영 | chaeum-ai.kr + EC2 | 서버 공유 저장소의 자료 DB·요청 DB, 서버 `.env` | 서비스 |

운영과 똑같은 별도 스테이징 서버는 두지 않았습니다. 서버가 한 대라 **CI 검사 → 미리보기 → 배포 직전 재검사 → 헬스체크를 통과해야 전환**하는 단계로 막습니다.

## 백엔드 배포 흐름

develop에 push되면(또는 Actions에서 「배포」를 직접 실행하면) 자동으로 돕니다. 배포는 한 번에 하나만 실행됩니다.

```text
검사: ruff · ruff format · mypy · unittest        ← 실패하면 여기서 멈추고 배포하지 않음
→ AWS 인증(OIDC — GitHub에 AWS 키를 저장하지 않음)
→ backend/·deploy/ 를 묶어 S3에 업로드
→ SSM으로 EC2에서 deploy/deploy.sh 실행
    1. 지금 쉬는 포트(8001/8002)에 새 버전을 띄움
    2. 새 포트의 /health를 최대 60초 확인 — 실패하면 전환하지 않고 중단(구 버전이 계속 서비스)
    3. nginx가 새 포트를 보게 바꾸고 reload — 기존 연결은 유지, 새 요청만 옮겨 감
    4. 구 버전 정지, 재부팅 때 올라올 쪽도 새 포트로
    5. 릴리스는 최근 3개만 남김
→ 외부에서 https://kangwon-1-chaeum.duckdns.org/health 200 확인 — 아니면 워크플로 실패로 표시
```

근거: [deploy.yml](../.github/workflows/deploy.yml) · [deploy.sh](../deploy/deploy.sh) · [chaeum@.service](../deploy/chaeum@.service)

## 서버 구성

| 항목 | 값 |
| --- | --- |
| 설치 위치 | `/opt/chaeum` — `releases/<커밋>`, 지금 버전을 가리키는 `current` 링크, `shared` |
| 공유 폴더 | `shared/.env` · `shared/storage` · `shared/cache` · `shared/venv` — 배포가 덮어쓰지 않고 릴리스에 링크로 연결 |
| 요청 DB | `SQLITE_PATH=/opt/chaeum/shared/storage/chaeum.sqlite3` |
| 자료 DB | `LOCAL_DATA_DB_PATH=/opt/chaeum/shared/storage/market_data.sqlite3` (서울 전체, 약 0.8GB) |
| 실행 | systemd 템플릿 `chaeum@8001` / `chaeum@8002`, 워커 1개(분석 작업표가 프로세스 메모리에 있어서) |
| 앞단 | nginx — `deploy.sh`가 `/etc/nginx/conf.d/chaeum-upstream.conf`의 포트 한 줄만 바꿈 |
| AWS | 서울 리전 · S3 `ktc4-kangwon-1-deploy` · SSM · IAM 역할 `ktc-github-deploy`(OIDC) |
| 로그 | 배포 `/var/log/chaeum-deploy.log`, 앱 `journalctl -u chaeum@8001`(또는 8002) |

## 비밀 값

- **서버:** `/opt/chaeum/shared/.env` — LLM·카카오 등 키. 변수 이름은 `backend/.env.example`에 있습니다. git에는 올리지 않습니다.
- **GitHub:** AWS 키를 저장하지 않고 OIDC로 역할을 빌립니다. 저장소 변수는 `AWS_ACCOUNT_ID` 하나입니다.
- **Vercel:** `NEXT_PUBLIC_API_BASE_URL`(운영은 `https://api.chaeum-ai.kr`)·`NEXT_PUBLIC_KAKAO_MAP_APP_KEY`는 Vercel 프로젝트 환경 변수로 둡니다.
- **CORS:** 화면 주소는 백엔드 `CORS_ALLOW_ORIGINS`에 쉼표로 이어 붙입니다.

## 자료 DB — 분기 갱신

앱은 자료 DB를 만들지 않고 **읽기만** 합니다. 요청마다 활성 자료 버전을 고정해서 읽습니다.

- **갱신:** `backend/scripts/refresh_local_data.py`가 분기 자료를 적재 → 검증 → 활성화합니다. 실패하면 이전 버전을 그대로 씁니다.

  ```bash
  cd backend
  python scripts/refresh_local_data.py --help
  python scripts/refresh_local_data.py --quarter 20262 --seoul-csv <서울 CSV> --dry-run   # 파일만 검증
  ```

- **서버 반영:** 갱신한 자료 DB를 서버 `shared/storage`에 올리는 단계는 아직 수동입니다. 실행 중인 파일을 그 자리에서 덮지 말고, 새 이름으로 올려 검증한 뒤 바꿉니다. 기존 자료 DB를 지워서 초기화하지 않습니다.

## 되돌리기

- 새 버전이 내부 `/health`를 통과하지 못하면 **자동으로 전환하지 않습니다.** 구 버전이 그대로 서비스합니다.
- 전환한 뒤 문제가 보이면: develop에서 원인 커밋을 `git revert` → push → 같은 흐름으로 다시 배포합니다. 검사·헬스체크를 다시 거치므로 가장 안전합니다.
- 서버에는 최근 릴리스 3개가 남아 있어, 급하면 이전 릴리스로 직접 되돌릴 수 있습니다. 다만 가상환경(`shared/venv`)은 릴리스끼리 함께 쓰므로 의존성까지 이전 상태로 돌아가지는 않습니다.

## 왜 Docker 대신 systemd인가

백엔드는 EC2 한 대에서 FastAPI 프로세스 하나만 돌고, DB는 파일(SQLite)이며, 화면은 Vercel이 따로 배포합니다. 함께 띄울 서비스가 없어서 컨테이너 대신 systemd 서비스 두 개(8001/8002)와 nginx 전환으로 무중단 배포를 했습니다. 0.8GB 자료 DB는 분기마다 바뀌어 이미지에 넣을 수 없고, 컨테이너를 써도 볼륨으로 따로 붙여야 해서 지금 방식(`shared/storage` 링크)과 같습니다. 서버가 여러 대가 되거나 DB를 PostgreSQL로 옮기면 컨테이너로 바꿉니다.

## 알려진 한계와 다음 단계

| 한계 | 지금 대응 | 다음 단계 |
| --- | --- | --- |
| 서버 한 대, 스테이징 없음 | 배포 직전 재검사 · 헬스체크 통과 후 전환 | 서버를 늘릴 때 스테이징 분리 |
| `/health`는 자료 DB 준비까지 확인하지 않음 | 자료 DB는 공유 저장소에 두고 배포가 건드리지 않음 | 자료 버전까지 보는 `/health/ready` |
| 자료 DB 서버 반영이 수동 | 갱신 스크립트가 검증 후 활성화, 실패 시 이전 버전 유지 | S3를 거친 업로드·교체 자동화 |
| 의존성 잠금 파일 없음 | Python 3.12 고정, 배포 직전 같은 검사 | lock 파일 추가 |
| 전환 뒤 문제는 자동 복구 안 됨 | 외부 `/health` 확인, revert 후 재배포 | 롤백 스크립트 |
