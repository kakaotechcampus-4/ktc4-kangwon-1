# 백엔드 배포·운영

2026-10-26 저장소 코드 기준. 서버 접속·실제 배포는 이번에 수행하지 않았다. 배포 URL·서버 nginx 설정은 운영자 확인 전에는 기재하지 않는다.

## 코드에서 확인한 배포 흐름

근거: [deploy.yml](../.github/workflows/deploy.yml), [deploy.sh](../deploy/deploy.sh), [systemd 서비스](../deploy/chaeum@.service).

```text
develop push 또는 수동 실행
→ Ruff·포맷·mypy·unittest
→ AWS OIDC 인증 → backend 배포 묶음 S3 업로드
→ SSM으로 EC2의 deploy.sh 실행
→ 8001/8002 중 비활성 포트 시작 → 내부 /health 확인
→ nginx 검사·전환 → 이전 서비스 종료 → 외부 /health 확인
```

| 항목 | 저장소에서 확인한 값 |
| --- | --- |
| 설치 루트 | `/opt/chaeum` |
| 환경 파일 | `/opt/chaeum/shared/.env`를 릴리스에서 연결 |
| 요청 DB | `SQLITE_PATH=/opt/chaeum/shared/storage/chaeum.sqlite3` |
| 자료 DB | `LOCAL_DATA_DB_PATH=/opt/chaeum/shared/storage/market_data.sqlite3` |
| 릴리스 | 최근 3개 보관, `current` 심볼릭 링크 전환 |
| 실행 | 포트별 systemd 서비스 `chaeum@8001`, `chaeum@8002`, 기본 worker 1개 |
| 로그 | `/var/log/chaeum-deploy.log`, `journalctl -u chaeum@8001` 또는 `chaeum@8002` |

## 자료 DB 준비

앱 기동 시 요청 DB를 초기화하지만 자료 DB를 자동 다운로드·생성하지 않는다. 일반 분석의 `LocalAdapter`는 자료 DB를 읽기 전용으로 열고 활성 자료 버전을 확인한다. 파일이 없거나 활성 버전이 없으면 분석은 실패한다. `/health` 성공만으로 자료 준비를 보증할 수 없다.

현재 갱신 도구는 `backend/scripts/refresh_local_data.py`다. 계획에 있던 `update_local_market_data.py`는 없다. 이 도구는 입력 CSV·SHP와 API 조회 자료를 적재하고 버전을 활성화한다. 필요한 파일·옵션은 다음으로 확인한다.

```powershell
cd backend
python scripts/refresh_local_data.py --help
```

실제 갱신에는 외부 호출·자료가 필요하므로 별도 승인·자료 준비 후 실행한다. 저장소에는 운영 서버 최초 자료 DB 업로드 자동화가 없다. **전송 수단·담당자·정기 갱신 절차는 미정(운영자 확인 필요)**이다. 실행 중 SQLite 파일 하나만 복사하지 말고 일관된 백업·검증 후 교체하는 절차부터 합의해야 한다. 기존 자료 DB를 삭제해 초기화하지 않는다.

## 복구 범위와 남은 결정

새 포트의 내부 건강 검사가 실패하면 새 서비스를 중단하고 `current`를 이전 릴리스로 돌린다. 모든 단계의 자동 롤백은 아니다. nginx 전환 실패·외부 검사 실패의 완전 복구, 공유 가상환경 의존성의 이전 버전 복원까지 보장하지 않는다.

- `/health`는 기존 전환 조건으로 유지한다. 자료 DB 준비 상태를 별도로 검사하는 `/health/ready`는 제안이며 미구현이다.
- 명시적인 롤백 스크립트와 자료 DB 배포 절차도 후속 과제다. 이번에는 deploy.yml·deploy.sh·서비스 파일을 수정하지 않았다.
- nginx 구성·서버 비밀 값·dev/prod 분리는 추정하거나 새로 작성하지 않았다.
