# 별칭 동시성 수정·홍대 실측·수동 push 점검 — 2026-10-14

**실테스트 품질 기준 미통과.** DB 잠금 없이 completed/결과 계약 검증까지104.219초에 끝났다.
L직접51개·G51개·C4여섯 개는 확인했지만 평가완료2/4·피드백 유효 반영0이다.
사용자가 “push는 내가할게”로 변경하여 push·PR생성은하지 않았다.
프롬프트·모델/토큰/시간 상한은바꾸지 않았고 한 회 뒤재실행하지 않았다.

## 수정

별칭 없음 조회 후 INSERT가 무시되면 기존 코드는 counter만 늘려
같은 fact_id의 UNIQUE 충돌을 계속 시도할 수 있었다.
사실 참조 수집/출력 변환은 트랜잭션 밖으로 옮겼다.
BEGIN IMMEDIATE로 짧은쓰기 트랜잭션을잡고 기존별칭을확인한다.
INSERT의 UNIQUE/PRIMARY KEY 충돌이면 같은fact_id의 기존별칭을 다시읽고,
다른별칭 충돌이면 최대8회 재시도한다. 초과는 오류·트랜잭션 rollback이다.
FK/트리거 오류는충돌로숨기지않고전파한다.

쓰기 연결은 요청 DB·초기화·로컬 자료 갱신·재생 복사 모두30,000ms로통일했다.
자료 DB 파일은수정하지않았다. 읽기전용 연결의5초는별도다.
평가자 녹화 재생을시험하기 위해 ReplayGenerate의 허용역할을 네평가자로 확장했다.
기존 도구/자문 응답구분·검증을유지했다. 모델런타임의 프롬프트는변경하지않았다.

| 회귀 | 결과 |
| --- | --- |
| 같은51fact를 동시8작업별칭생성 | 10초제한 안 종료·별칭동일/유일 |
| 강제별칭충돌 | 정확히8회후오류·rollback·기존별칭보존 |
| 쓰기연결 busy_timeout | 요청/로컬자료30,000ms |
| 평가4명 녹화 재생+decision저장8회 | 10초제한 안 종료·완료4/4·최종재계산 |

수정 커밋:48b931b.

## 반복문 전수 점검

범위는 backend/app와 backend/scripts의 while, 성공/재시도 표현, to_thread와 재시도for다.
동기·스레드 작업의 무한재시도는별칭 한곳이었다. 나머지 동기 반복은유한진행을확인했다.
아래 비동기 대기/모델루프를 같은종류의스레드재시도로분류하지 않았다.

| 위치 | 종류·종료근거 | 처리 |
| --- | --- | --- |
| agentic/aliases.encode | 동기 충돌재시도 | while True 제거, range(8)+기존fact 재조회 |
| business_lifecycle/area_resolver SHP | 동기offset·파일길이 | 길이검증≥2words, offset증가, 유한·유지 |
| business_lifecycle/area_resolver DBF | 동기offset·헤더길이 | 32바이트씩증가, 유한·유지 |
| scripts/validate_c1_alpha 두while | 동기정렬그룹순회 | start/end 증가·목록길이유한·유지 |
| services/analysis 실패원인순회 | 동기cause연쇄 | 최대4개·유지 |
| agentic/runtime 응답축소 | 메모리목록 | entries.pop으로감소·유지 |
| agentic/sql_tool 응답축소 | 메모리목록 | rows.pop으로감소·유지 |
| local_data/refresh 재시도 | async+스레드DB 호출 | range(2), 고정페이지목록·쿼터·유지 |
| commercial_area/map_analysis client 재시도 | asyncHTTP | 설정횟수range, 요청timeout·유지 |
| education_zone 재시도 | asyncHTTP | 설정횟수range(검증상한5), 수정금지·유지 |
| scripts/fetch_population_snapshot 재시도 | asyncHTTP | 설정횟수range·유지 |
| business_lifecycle/client.fetch_store_data | async페이지 while True | HTTPawait 취소가능·전체건수/빈페이지 종료, 새요청경로는로컬DB·유지 |
| agentic/runtime.run | async도구루프 while True | 모델/토큰/시간 예산·제출/질문/실패 종료·유지 |
| agentic/evaluators.review | async모델루프 | 읽기3·제출수정2·전역안전선·유지 |
| scripts/measure_lifecycle_baseline | async페이지 | MAX_REQUESTS50·유지 |
| scripts/measure_backend_load.sample | async계측 while True | sleep await·종료시 task.cancel, 스레드아님·유지 |
| concurrency.run_in_thread | async스레드완료대기 | worker 종료를기다림. worker의무한재시도제거·유지 |
| llm/session 종료대기 | asyncclient완료대기 | 완료task/await·유지 |
| floating_population/client 정리대기 | async완료task | 종료task/await·유지 |

## 실제 실행

| 항목 | 결과 |
| --- | --- |
| 요청 | e39bd8b5abbb43fbb8e4906dfb057b47 |
| 주소·시험답변 | 서울 마포구 와우산로94 / 1층 / 약40㎡ / 이전일반소매·주방배기없음 |
| 공개API | POST → events → 질문 → answers → GET completed |
| 전체시간 | 104.219초 |
| 모델완료호출 | 28회, 실제model=gpt-6-luna, 자문0회 |
| 입력/출력 | 290,281 / 14,868토큰 |
| L직접채택 | 51개, 거절0개, unknown0개 |
| L등급 | 1등급18개·2등급33개. 0/3/4는0개 |
| 규제 | G51개해당없음(제한관련4업종포함) |
| 시설 | C4적용6개observed, 나머지45개n.a. |
| 초안 | 한 번 제출·채택 |
| 평가 | customer/landlord_advocate completed, examiner/founder failed=INVALID_REFERENCE |
| 피드백 | 한 회시도·최종제출2회거절·유효반영0 |
| 결과 | DecisionResult 검증통과, review_completeness=0.5, 피드백미완료명시 |
| DB잠금·저장실패 | 없음 |

## 통과 기준

| 기준 | 판정 |
| --- | --- |
| 계약통과·최종보고서거절없음 | 미통과: 계약은통과, 최종제출2회거절후유효초안으로마무리 |
| 직접L≥45 | 통과:51 |
| 평가완료4·유효피드백1 | 미통과:2/4·0 |
| G/C4관측 | 통과:51/6 |
| 소매주방·배기부재불리요인없음 | 통과:해당component adverse0 |

평가자는빈근거나문장숫자를제출했다. founder는R104를설명문에쓴것도숫자검증에걸렸다.
examiner는빈근거2건과G203/L102 같은식별자문장을반복해추가수정2회뒤실패했다.
customer는빈근거, landlord는1층표현을고친뒤완료했다.
현재숫자검증은숫자지표뿐아니라업종식별자의숫자도차단한다.
이는남은검증정책문제이며이번에는고치지않는다.

완료된두평가자의조건부지적6건은공간요건이미검토초안임·환기미확인·건축물용도확인이다.
decision의 최종review_resolutions도숫자문장검증에두번걸려최종단계호출몫을소진했다.
전체400k/60k/40회/600초안전선은넘지않았다. 최종결과에피드백미완료를남겼다.
수용/일부/기각의유효저장기록은없다. 추가튜닝·상한조정·재실행하지않았다.

## L 반영 후 제공된 Top5

| 순위 | 업종 | 코드 | L | 하한/적용배점 | 배지 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | G203 모터사이클·운동용품·자전거 소매 | 63.125 | 5 | 68.125/90 | 추천 |
| 2 | G213 문화·오락·여가용품 소매 | 57.5 | 5 | 62.5/100 | 보류 |
| 3 | G208 가전·정보통신장비 소매 | 55.625 | 5 | 60.625/90 | 추천 |
| 4 | R104 오락 서비스 | 55.625 | 5 | 60.625/90 | 추천 |
| 5 | G204 종합 소매 | 48.75 | 5 | 53.75/80 | 추천 |

평가일부·최종피드백미완료인결과다. 공간요건은모두미검토추정이므로확정운영요건이아니다.

## 호출별측정

번호는녹화완료순서다. 병렬시작순서와다를수있다. HTTP응답과도구검증성공은별개다.

| 번호 | 역할 | 도구 | 입력 | 출력 | 초 |
| --- | --- | --- | ---: | ---: | ---: |
| 1 | decision | get_scorecard | 7246 | 22 | 1.983 |
| 2 | decision | ask_user | 8055 | 173 | 2.969 |
| 3 | decision | get_facts | 8102 | 29 | 1.938 |
| 4 | decision | submit_l | 13880 | 2318 | 17.452 |
| 5 | decision | submit_draft | 22079 | 1574 | 15.297 |
| 6 | examiner | get_scorecard | 6758 | 22 | 1.328 |
| 7 | customer | get_facts | 6748 | 36 | 1.405 |
| 8 | founder | get_facts | 6758 | 36 | 1.5 |
| 9 | landlord_advocate | get_facts | 6760 | 47 | 2.546 |
| 10 | founder | get_facts | 5573 | 47 | 1.219 |
| 11 | examiner | get_facts | 11720 | 39 | 1.405 |
| 12 | customer | get_facts | 5971 | 47 | 1.422 |
| 13 | landlord_advocate | get_facts | 7198 | 32 | 1.219 |
| 14 | customer | get_scorecard | 7626 | 41 | 1.171 |
| 15 | landlord_advocate | get_facts | 7388 | 32 | 1.202 |
| 16 | examiner | get_facts | 11674 | 39 | 3.296 |
| 17 | founder | submit_review | 7309 | 485 | 5.625 |
| 18 | customer | submit_review | 11260 | 476 | 4.811 |
| 19 | landlord_advocate | submit_review | 8038 | 528 | 6.484 |
| 20 | founder | submit_review | 7823 | 480 | 3.702 |
| 21 | examiner | submit_review | 13863 | 673 | 6.765 |
| 22 | customer | submit_review | 9761 | 464 | 4.875 |
| 23 | founder | submit_review | 7016 | 433 | 3.625 |
| 24 | landlord_advocate | submit_review | 7248 | 464 | 4.889 |
| 25 | examiner | submit_review | 12089 | 471 | 4.686 |
| 26 | examiner | submit_review | 12616 | 480 | 4.141 |
| 27 | decision | submit_draft | 25629 | 2733 | 20.813 |
| 28 | decision | submit_draft | 24093 | 2647 | 16.953 |

| 역할 | 호출 | 입력 | 출력 |
| --- | ---: | ---: | ---: |
| decision | 7 | 109084 | 9496 |
| examiner | 6 | 68720 | 1724 |
| customer | 5 | 41366 | 1064 |
| founder | 5 | 34479 | 1481 |
| landlord_advocate | 5 | 36632 | 1103 |
| 전체 | 28 | 290281 | 14868 |

## 푸시전점검

push는사용자가직접하므로실행하지않는다. PR도생성하지않는다.

| 항목 | 점검결과 |
| --- | --- |
| a | 기록커밋후git status clean. 실제cache/storage/SQLite/녹화/임시스크립트 추적0. storage/.gitignore는설정파일 |
| b | 실제.env추적0, 인증키문자열발견0. LLM_MAX_TOKENS 숫자설정은인증비밀아니므로제외 |
| c | git diff origin/develop --stat -- .github 비어있음. 보호4파일차이0 |
| d | education_zone.py origin/develop diff0 |
| e | frontend diff0, 새파일5MiB초과0 |
| f | backend ruff/checkformat197파일·mypy103·unittest494(48.472초)·catalog·408재현통과. frontend format/lint/build통과 |
| g | fetch후develop보다앞60/뒤0(기록커밋포함). develop은조상으로병합충돌없음. merge/rebase없음 |

브랜치명은사용자지정 feat/agentic-decision이다. 문서의feature/*와다르지만이름을바꾸지않았다.
과거메시지규칙비일치목록:6aa2f64 merge: develop 반영(백엔드 리팩토링·교육환경보호구역·프론트) 및 51개 업종 체계 충돌 해결.
과거커밋은재작성하지않았다. 나머지앞선커밋은허용type·한국어제목이다.
perf/decision의앞선15커밋을포함한다.

origin/feat/agentic-decision은아직없다. 원격어느브랜치에도없는커밋은기록커밋포함60개다.
처음수동push에포함될앞쪽제목은다음과같다.

- 6818746 docs: 오래된 설계 문서와 검증 도구 안내 정리
- 50855ab feat: 유동인구 기준선 측정과 시간대별 규모 백분위 추가
- f9e326f feat: 서비스 업종 체계를 51개로 개편하고 분할 매핑 통합
- 2e45967 fix: 개폐업 상권 응답 내 누락 원천을 0으로 집계
- 6aa2f64 merge: develop 반영(백엔드 리팩토링·교육환경보호구역·프론트) 및 51개 업종 체계 충돌 해결

자동push0개. 원격해시일치검사는push하지않아해당없음이다.
프론트팀은결과2.0/도구3·fact슬롯·L51개·평가4슬롯·pending접수를맞춰야한다.
규제팀의education_zone함수는호출만하고바꾸지않았다. schemas.py 변경은PR팀계약검토대상이다.

## 보존

cache/alias-fix-live-hongdae/public-result.json·summary.json·requests.sqlite3와
e39bd8b5abbb43fbb8e4906dfb057b47-model-calls.json이있다.
콘솔은cache/alias-fix-live-console.log다. 이전자료를덮어쓰지않고모두커밋에서제외했다.
PR설명초안은채팅에만제공하며파일·PR을생성하지않는다.

