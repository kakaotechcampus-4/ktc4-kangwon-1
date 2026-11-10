# 법적 안내 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 개인정보 처리방침·이용약관 페이지, 가입 동의와 동의 기록, 개인정보를 덜 받는 변경, 옛 분석 막기, 질문 답 지우기 스크립트를 실험소 사본에 만든다.

**Architecture:** 서버는 기존 계층(api → application → ports → infrastructure)을 그대로 따른다. 동의 기록은 새 표 `terms_agreements`(DB 판 7)로 두고 계정 생성과 한 트랜잭션에서 쓴다. 화면은 법적 문서 두 장을 서버 컴포넌트로 만들고, 가입 화면에 공용 체크박스를 더한다.

**Tech Stack:** FastAPI · Python 3.12 · sqlite3 · unittest / Next.js 16 · React 19 · Tailwind v4 · Vitest

**Spec:** `docs/superpowers/specs/2026-11-08-legal-notice-design.md`

## Global Constraints

- 작업 위치: `C:\Users\super\Desktop\새 폴더 (13)\ktc4-kangwon-1-lab` (push 막힘). 브랜치 `feature/legal-notice`를 develop에서 딴다.
- **새 주석을 넣지 않는다.** 기존 주석은 유지하되, 사실이 바뀐 주석(카카오 사진 언급, 옛 요청 공개)은 사실에 맞게 고치거나 함께 지운다.
- 새 라이브러리 금지. `backend/.env` 열지 않음. 상대 import 금지.
- 커밋: `type: 한국어 요약`(feat·fix·test·docs·refactor), 한 커밋 한 가지, 도구 흔적(Co-Authored-By, Generated with 등) 넣지 않음.
- 서버 오류는 `AuthError("대문자_코드", "한국어 문장")`, HTTP 번호는 API가 정한다. 화면은 서버 `detail`을 그대로 보여 주므로 한국어여야 한다.
- 새 저장 함수는 `application/ports/storage.py` 창구와 이름·인자 1:1(`tests/test_storage_port.py`), 내부 헬퍼는 `_` 접두, SQL은 infrastructure에만.
- 화면 말투: 계정·법적 화면 합니다체, 분석 화면 해요체. 실패 문구 "…하지 못했습니다. 잠시 후 다시 시도해 주세요." 요청은 "~해 주세요"(띄어 씀). 색은 `@/styles/tokens`, 글자 크기는 `text-13/15/17` 스케일.
- 약관 판: `TERMS_VERSION = "v1"`. 처리방침·약관 시행일 칸은 `【배포일】`, 운영 주체 칸은 `【팀원 이름】`으로 둔다.
- 서버 시험 명령(`backend/`): `.venv/Scripts/python.exe -m unittest discover -s tests` — Windows에서는 `test_load_harness` 불러오기 오류 1건이 원래 있다.
- 화면 시험 명령(`frontend/`): `npm test`, `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm run build`.

## Review Focus

1. 한글 답이 JSON 안에 `\uXXXX`로 저장돼 있어도 지우기가 빠짐없이 된다 → Task 5 `test_korean_answer_is_erased_even_when_json_escaped`
2. 지우기 중간에 실패하면 아무것도 바뀌지 않고 지우기 금지 장치도 그대로다 → Task 5 `test_failure_rolls_back_and_keeps_triggers`
3. 동의 기록이 있는 계정도 탈퇴가 성공하고 기록이 남지 않는다 → Task 2 `test_withdraw_removes_terms_agreement`
4. 동의 기록이 없는 기존 카카오 계정도 로그인이 되고, 그때 동의 행을 새로 만들지 않는다 → Task 3 `test_existing_kakao_user_logs_in_without_new_agreement`
5. 가입 중 약관 링크를 눌러도 입력한 값이 사라지지 않는다(새 탭으로 연다) → Task 7 `약관 링크는 새 탭으로 연다`

---

### Task 0: 브랜치와 설계 문서 커밋

- [ ] **Step 1:** `git switch develop && git switch -c feature/legal-notice`
- [ ] **Step 2:** 설계·계획 문서 커밋

```bash
git add docs/superpowers/specs/2026-11-08-legal-notice-design.md docs/superpowers/plans/2026-11-08-legal-notice.md
git commit -m "docs: 법적 안내 설계와 구현 계획"
```

### Task 1: 약관 동의 기록 표와 DB 판 7

**Files:**
- Create: `backend/app/domain/terms.py`
- Modify: `backend/app/infrastructure/persistence/schema.sql` (계정 구역 끝, `analysis_owners` 다음), `backend/app/infrastructure/persistence/connection.py:18-28`
- Test: `backend/tests/test_db_migration.py`
- Docs: `docs/DATABASE.md`(요청 DB 버전 문단 `:109-113`, 계정과 세션 표 `:365-373`)

**Interfaces:**
- Produces: `app.domain.terms.TERMS_VERSION: str = "v1"`, 표 `terms_agreements(user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE, terms_version TEXT NOT NULL, method TEXT NOT NULL CHECK (method IN ('email','kakao')), agreed_at TEXT NOT NULL, PRIMARY KEY (user_id, terms_version))`

- [ ] **Step 1: 실패하는 시험** — `test_db_migration.py`의 v5 시험(`test_auth_tables_are_added_to_a_version_five_database`)과 같은 방식으로:

```python
def test_terms_table_is_added_to_a_version_six_database(self):
    # 새 파일을 만들고 사용자 1명을 넣은 뒤 terms_agreements를 지우고 user_version=6으로 내린다
    # initialize 후:
    self.assertEqual(_user_version(path), 7)
    self.assertIn("terms_agreements", tables)
    self.assertEqual(user_count, 1)

def test_deleting_user_cascades_terms_agreement(self):
    # users 1행 + terms_agreements 1행을 넣고 DELETE FROM users 실행
    self.assertEqual(agreement_count, 0)
```

- [ ] **Step 2:** `-m unittest tests.test_db_migration -v` → 두 시험 실패(버전 6, 표 없음)
- [ ] **Step 3:** `domain/terms.py`에 상수, `schema.sql`에 표, `connection.py`에 `SCHEMA_VERSION = 7`, `_UPGRADABLE_FROM = frozenset({5, 6})`, `_REQUIRED_TABLES`에 `"terms_agreements"`. 기존 `test_new_file_gets_current_version` 등은 상수를 쓰므로 그대로 통과해야 한다.
- [ ] **Step 4:** 같은 명령 → 전부 통과. `docs/DATABASE.md`를 버전 7·`{5, 6}`·표 설명 한 줄로 고친다.
- [ ] **Step 5:** `git commit -m "feat: 약관 동의 기록 표와 요청 DB 판 7"`

### Task 2: 이메일 가입 동의와 이름 칸 제거

**Files:**
- Modify: `backend/app/infrastructure/persistence/repository/users.py:37-50`, `backend/app/application/ports/storage.py:201`, `backend/app/application/auth.py:96-118`, `backend/app/application/services.py:54-57`, `backend/app/api/v1/auth.py:44-48,105-122`
- Modify(호출부): `backend/scripts/create_e2e_user.py:12`, `backend/scripts/measure_backend_load.py:279`, `backend/tests/auth_fixture.py:34`
- Test: `backend/tests/test_auth_api.py`
- Docs: `docs/API_CONTRACT.md:80`

**Interfaces:**
- Consumes: `TERMS_VERSION`, 표 `terms_agreements` (Task 1)
- Produces:
  - `users.create_email_user(email: str, password_hash: str, terms_version: str, *, db_path=None) -> str` — users 행(display_name NULL)과 `terms_agreements`(method `'email'`)를 한 `with connect(...)` 안에서 넣는다. 중복 이메일은 지금처럼 `EmailTaken`.
  - `auth.signup(email, password, agree_terms: bool, *, db_path=None, mail, auth, client=None) -> tuple[str, bool]` — `agree_terms`가 거짓이면 다른 일을 하기 전에 `AuthError("TERMS_REQUIRED", "이용약관에 동의해야 가입할 수 있습니다.")`
  - `AuthService.signup(self, email, password, agree_terms, *, mail, auth)`
  - `SignupBody`: `email`, `password`, `agree_terms: bool = False` (`display_name` 삭제, `extra="forbid"` 유지)
  - API: `AuthError` 중 `TERMS_REQUIRED`는 422, 나머지는 지금처럼 409

- [ ] **Step 1: 실패하는 시험** (`test_auth_api.py`, 기존 가입 도우미의 본문에서 `display_name`을 빼고 `agree_terms: True`로 바꾼다)

```python
def test_signup_without_terms_agreement_is_422(self):
    response = self.client.post("/api/v1/auth/signup", json={"email": ..., "password": ...}, headers=ORIGIN)
    self.assertEqual(response.status_code, 422, response.text)
    self.assertEqual(response.json()["detail"], "이용약관에 동의해야 가입할 수 있습니다.")
    # users 행 0개

def test_signup_records_terms_agreement(self):
    # agree_terms=True로 가입 → 201
    self.assertEqual(rows, [(user_id, "v1", "email")])  # (user_id, terms_version, method)

def test_signup_rejects_display_name(self):
    # 본문에 display_name 포함 → 422

def test_withdraw_removes_terms_agreement(self):
    # 가입 → DELETE /api/v1/auth/me → 200, terms_agreements 행 0개, users 행 0개
```

- [ ] **Step 2:** `-m unittest tests.test_auth_api -v` → 새 시험 실패
- [ ] **Step 3:** 위 Produces대로 구현하고 호출부 세 곳을 `create_email_user(email, digest, TERMS_VERSION, db_path=...)`로 고친다(`auth_fixture.create_user`의 이름 인자는 쓰지 않게 정리하고, 그 인자를 넘기던 시험도 함께 고친다).
- [ ] **Step 4:** `-m unittest tests.test_auth_api tests.test_storage_port tests.test_architecture -v` → 통과. `docs/API_CONTRACT.md` 가입 줄을 `email·password(10자 이상)·agree_terms(참). 동의 없으면 422`로 고친다.
- [ ] **Step 5:** `git commit -m "feat: 이메일 가입 약관 동의와 동의 기록, 이름 입력 제거"`

### Task 3: 카카오 동의 기록과 프로필 사진 중단

**Files:**
- Modify: `backend/app/application/ports/identity.py:71-79`, `backend/app/infrastructure/clients/kakao_oauth.py:99-112`, `backend/app/infrastructure/persistence/repository/users.py:53-87`, `backend/app/application/ports/storage.py:202-204`, `backend/app/application/auth.py:82-92,259-266`
- Test: `backend/tests/test_auth_kakao.py`
- Docs: `docs/API_CONTRACT.md:83`

**Interfaces:**
- Consumes: `TERMS_VERSION` (Task 1)
- Produces:
  - `KakaoProfile(provider_user_id: str, nickname: str | None)` — `__slots__ = ("provider_user_id", "nickname")`
  - `users.link_or_create_social_user(provider: str, provider_user_id: str, terms_version: str, *, nickname: str | None = None, db_path=None) -> str` — 새 계정: users(profile_image_url NULL)·user_identities·terms_agreements(method `'kakao'`)를 한 트랜잭션. 기존 계정: `last_login_at` 갱신과 `profile_image_url = NULL`만, 동의 행은 만들지 않는다.
  - `public_user`에서 `profile_image_url` 키 삭제

- [ ] **Step 1: 실패하는 시험**

```python
def test_new_kakao_user_records_terms_agreement(self):
    # 카카오 콜백으로 새 계정 생성
    self.assertEqual(rows, [(user_id, "v1", "kakao")])

def test_existing_kakao_user_logs_in_without_new_agreement(self):
    # 동의 행 없는 기존 카카오 계정을 직접 넣고(profile_image_url='https://img') 콜백
    self.assertEqual(callback.status_code, 302)
    self.assertEqual(agreement_count, 0)
    self.assertIsNone(stored_profile_image_url)

def test_me_has_no_profile_image_url(self):
    self.assertNotIn("profile_image_url", me.json())
```

- [ ] **Step 2:** `-m unittest tests.test_auth_kakao -v` → 실패
- [ ] **Step 3:** Produces대로 구현. 카카오 응답에서 사진 주소를 읽지 않는다. `KakaoProfile` 설명의 "닉네임·사진" 문구는 "닉네임"으로 고친다.
- [ ] **Step 4:** `-m unittest tests.test_auth_kakao tests.test_auth_api tests.test_storage_port -v` → 통과. `docs/API_CONTRACT.md`의 `/auth/me` 필드 목록에서 `profile_image_url`을 뺀다.
- [ ] **Step 5:** `git commit -m "feat: 카카오 가입 동의 기록과 프로필 사진 저장 중단"`

### Task 4: 주인 없는 옛 분석 막기

**Files:**
- Modify: `backend/app/infrastructure/persistence/repository/requests.py:37-53`, `backend/app/infrastructure/persistence/repository/__init__.py:22`, `backend/app/application/requests.py:23-30`
- Test: `backend/tests/test_analysis_ownership.py:109-125`
- Docs: `docs/DATABASE.md:383-385`

**Interfaces:**
- Produces: `requests.owner_of(request_id, *, db_path=None) -> str | None` — 소유자 user_id, 소유자가 없거나 요청이 없으면 `None`. `LEGACY_OWNER_CUTOFF` 삭제. `visible_to`는 `owner is not None and user is not None and user["user_id"] == owner`.

- [ ] **Step 1: 실패하는 시험** — `test_requests_from_before_auth_stay_readable`을 아래로 바꾼다(기존 cutoff 이후 시험은 이것과 겹치므로 지운다).

```python
def test_ownerless_requests_are_hidden_regardless_of_age(self):
    # created_at '2026-10-01T00:00:00+00:00'인 소유자 없는 요청
    self.assertEqual(self.client.get("/api/v1/analyses/legacy").status_code, 404)
    # 로그인한 다른 사용자로도 404
```

- [ ] **Step 2:** `-m unittest tests.test_analysis_ownership -v` → 실패(200)
- [ ] **Step 3:** Produces대로 구현. "인증 전 요청만 열어 둔다"는 기존 주석은 함께 지운다.
- [ ] **Step 4:** 같은 명령과 `tests.test_storage_port` 통과. `docs/DATABASE.md` 옛 요청 문단을 "소유자가 없는 요청은 아무도 열 수 없다"로 고친다.
- [ ] **Step 5:** `git commit -m "fix: 소유자 없는 옛 분석 기록을 아무도 열 수 없게 막기"`

### Task 5: 질문 답 지우기

**Files:**
- Create: `backend/app/infrastructure/persistence/repository/erasure.py`, `backend/scripts/erase_user_answers.py`, `backend/tests/test_answer_erasure.py`
- Modify: `backend/app/application/ports/storage.py`(`RequestStore`), `backend/app/infrastructure/persistence/stores.py:71`(`_Modules(requests, analyses, events, erasure)`), `backend/tests/test_storage_port.py:27`(`port.RequestStore: (requests, analyses, events, erasure)`)
- Docs: `docs/DATABASE.md` 계정과 세션 절 끝에 "질문 답 지우기" 사용법 3~4줄

**Interfaces:**
- Produces:
  - `erasure.erase_user_answers(request_id: str, *, db_path=None) -> int` — 바꾼 행 수. 창구 `RequestStore.erase_user_answers(self, request_id, *, db_path=...) -> int`
  - 스크립트: `python scripts/erase_user_answers.py <db_path> <request_id>` → 바꾼 행 수를 한 줄로 출력, 없는 요청이면 0
- 정해진 방식(시그니처가 정하지 못하는 부분):
  1. 지울 글 = 그 요청의 사용자 답 값(`facts`의 `source='user'` 값과 질문 기록의 답). 선택지와 자유 글을 가를 수 없으면 답 값을 모두 지울 글로 본다.
  2. 한 연결·한 트랜잭션: `sqlite_master`에서 요청 DB의 `immutable_*` 트리거 SQL을 읽어 두고 DROP → DB의 모든 표·모든 TEXT 칼럼에서 지울 글을 원문 그대로와 JSON 이스케이프(`json.dumps(text)[1:-1]`) 두 형태로 찾아 `[삭제됨]`(이스케이프 칼럼에는 같은 방식으로 이스케이프한 값)으로 바꾼다 → 읽어 둔 트리거 SQL을 다시 실행 → 커밋. 어느 단계든 예외면 전체 롤백.
  3. 표 목록은 하드코딩하지 않고 `sqlite_master`에서 읽는다(답이 들어가는 곳이 facts·질문·실행 기록·원문·결과 등 여러 곳이라서).

- [ ] **Step 1: 실패하는 시험** (`test_agentic_public_api.py`의 `test_public_mock_question_resume_final_events` 흐름으로 질문 답을 넣는다. 답은 `"홍길동 010-1234-5678"`)

```python
def test_korean_answer_is_erased_even_when_json_escaped(self):
    self.assertGreater(_hits(path, SENTINEL), 0)        # 전제: 답이 실제로 저장됨
    changed = erasure.erase_user_answers(request_id, db_path=path)
    self.assertGreater(changed, 0)
    self.assertEqual(_hits(path, SENTINEL), 0)          # 원문·이스케이프 둘 다 0
    self.assertEqual(client.get(f"/api/v1/analyses/{request_id}").status_code, 200)

def test_triggers_are_restored(self):
    self.assertEqual(_trigger_names(path), before)      # 지운 뒤 트리거 목록이 그대로

def test_failure_rolls_back_and_keeps_triggers(self):
    # 바꾸는 단계에서 예외가 나게 patch → 예외 전파
    self.assertGreater(_hits(path, SENTINEL), 0)
    self.assertEqual(_trigger_names(path), before)

def test_unknown_request_changes_nothing(self):
    self.assertEqual(erasure.erase_user_answers("missing", db_path=path), 0)

def test_script_prints_changed_count(self):
    # subprocess로 스크립트 실행 → 출력이 숫자 한 줄
```

`_hits(path, text)`는 모든 표·TEXT 칼럼에서 `text`와 `json.dumps(text)[1:-1]`이 들어간 행 수를 센다(시험 파일 안 도우미). 전제 단언이 실패하면(모의 흐름이 답을 저장하지 않으면) `application/answers.record_answers`를 직접 부르는 준비로 바꾼다.

- [ ] **Step 2:** `-m unittest tests.test_answer_erasure -v` → 실패(모듈 없음)
- [ ] **Step 3:** 구현. 스크립트는 `create_e2e_user.py`처럼 인자를 받고 저장소 모듈을 직접 부른다.
- [ ] **Step 4:** `-m unittest tests.test_answer_erasure tests.test_storage_port tests.test_architecture -v` → 통과. `docs/DATABASE.md`에 사용법을 쓴다(메일 요청 → 계정 주인 확인 → 스크립트 실행, AI 제공자에게 이미 전달된 내용은 지울 수 없음).
- [ ] **Step 5:** `git commit -m "feat: 운영자용 질문 답 지우기 스크립트"`

### Task 6: 개인정보 처리방침·이용약관 페이지

**Files:**
- Create: `frontend/components/legal/LegalDocument.tsx`, `frontend/lib/legal/privacy.ts`, `frontend/lib/legal/terms.ts`, `frontend/app/privacy/page.tsx`, `frontend/app/terms/page.tsx`, `frontend/app/privacy/page.test.tsx`, `frontend/app/terms/page.test.tsx`

**Interfaces:**
- Produces:
  - `type LegalSection = { title: string; paragraphs?: string[]; items?: string[]; table?: { head: string[]; rows: string[][] } }`
  - `type LegalDoc = { eyebrow: string; title: string; effectiveDate: string; intro: string; sections: LegalSection[] }`
  - `export const PRIVACY: LegalDoc`, `export const TERMS: LegalDoc` (`lib/legal/*`)
  - `export default function LegalDocument({ doc }: { doc: LegalDoc })` — `my/reports` 페이지 틀(880 폭, `Header`, 영문 eyebrow, h1, 설명)에 섹션마다 `Card` + `h2 text-xl font-extrabold` + 본문 `text-base leading-relaxed text-[#4B5866] break-keep`. 표는 `<table>`(가로 스크롤 감싸기). `text-15` 미만 금지.
  - 페이지: 서버 컴포넌트, `export const metadata = { title: '채움 · 개인정보 처리방침' }` / `'채움 · 이용약관'`, 본문은 `<LegalDocument doc={PRIVACY} />`
- 내용: 처리방침은 설계 문서 7절 12항목 순서, 사실은 6절 표에서만. 약관은 8절 골격. 맨 위 안내 문장에 "출시 전 법률 검토 중인 초안"을 밝힌다. 운영 주체 `【팀원 이름】`, 시행일 `【배포일】`.

- [ ] **Step 1: 실패하는 시험** (`Header`는 `vi.mock`으로 null)

```tsx
describe('개인정보 처리방침 화면', () => {
  it('제목과 보호책임자 연락처를 보여 준다', () => {
    render(<PrivacyPage />);
    expect(screen.getByRole('heading', { level: 1, name: '개인정보 처리방침' })).toBeTruthy();
    expect(document.body.textContent).toContain('최용빈');
    expect(document.body.textContent).toContain('privacy@chaeum-ai.kr');
    expect(document.body.textContent).toContain('chaeum_session');
  });
});
describe('이용약관 화면', () => {
  it('만 14세 이상만 가입할 수 있다고 알린다', () => {
    render(<TermsPage />);
    expect(screen.getByRole('heading', { level: 1, name: '이용약관' })).toBeTruthy();
    expect(document.body.textContent).toContain('만 14세');
  });
});
```

- [ ] **Step 2:** `npm test -- app/privacy app/terms` → 실패(모듈 없음)
- [ ] **Step 3:** 구현
- [ ] **Step 4:** `npm test -- app/privacy app/terms` 통과, `npm run typecheck`, `npm run lint`
- [ ] **Step 5:** `git commit -m "feat: 개인정보 처리방침·이용약관 화면"`

### Task 7: 가입 동의 체크와 카카오 안내

**Files:**
- Create: `frontend/components/ui/Checkbox.tsx`, `frontend/app/signup/page.test.tsx`
- Modify: `frontend/app/signup/page.tsx:39,70,197-205`, `frontend/lib/api/auth.ts:10-19,48-61`, `frontend/components/auth/KakaoButton.tsx`

**Interfaces:**
- Consumes: 서버 `SignupBody.agree_terms` (Task 2), `/terms`·`/privacy` (Task 6)
- Produces:
  - `export default function Checkbox({ id, checked, onChange, children }: { id: string; checked: boolean; onChange: (checked: boolean) => void; children: React.ReactNode })` — 네이티브 `<input type="checkbox">` + `<label htmlFor>`
  - `signup(input: { email: string; password: string; agreeTerms: boolean })` → 본문 `{ email, password, agree_terms }`
  - `AuthUser`에서 `profile_image_url` 삭제
  - 가입 화면: 이름 칸과 `displayName` 상태 삭제, 체크박스 문구 "만 14세 이상이며 [이용약관]에 동의합니다 (필수)", 아래 문장 "개인정보는 [개인정보 처리방침]에 따라 처리됩니다." 두 링크는 `target="_blank" rel="noopener noreferrer"`. 미체크 제출 시 `setError('이용약관에 동의해 주세요.')`.
  - `KakaoButton` 아래 안내 `text-13`: "카카오로 시작하면 만 14세 이상이며 [이용약관]에 동의하고 [개인정보 처리방침]을 확인한 것으로 봅니다." (가입·로그인 화면 둘 다 이 컴포넌트를 쓰므로 한 곳만 고친다)

- [ ] **Step 1: 실패하는 시험** (`next/navigation`·`useAuth`·`@/styles/fonts` mock, `lib/api/auth`의 `signup`은 `vi.fn`)

```tsx
describe('회원가입 화면', () => {
  it('약관에 동의하지 않으면 가입 요청을 보내지 않는다', async () => {
    // 이메일·비밀번호 입력 후 가입하기
    expect(signup).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('이용약관에 동의해 주세요.');
  });
  it('동의하면 agreeTerms를 함께 보낸다', async () => {
    expect(signup).toHaveBeenCalledWith({ email: 'a@b.com', password: '1234567890', agreeTerms: true });
  });
  it('이름 칸이 없다', () => { expect(screen.queryByLabelText('이름')).toBeNull(); });
  it('약관 링크는 새 탭으로 연다', () => {
    expect(screen.getAllByRole('link', { name: '이용약관' })[0].getAttribute('target')).toBe('_blank');
  });
});
```

- [ ] **Step 2:** `npm test -- app/signup` → 실패
- [ ] **Step 3:** 구현
- [ ] **Step 4:** `npm test`, `npm run typecheck`, `npm run lint` 통과(`profile_image_url`을 쓰던 시험이 있으면 함께 고친다)
- [ ] **Step 5:** `git commit -m "feat: 가입 약관 동의 체크와 카카오 시작 안내"`

### Task 8: 바닥글 링크와 질문 답 안내

**Files:**
- Modify: `frontend/components/layout/Footer.tsx:57-60`, `frontend/components/analysis-progress/ClarifyingPanel.tsx:316-325`
- Create: `frontend/components/layout/Footer.test.tsx`

**Interfaces:**
- Produces:
  - 바닥글 상호 줄 옆에 `next/link`로 "이용약관"·"개인정보 처리방침"(처리방침은 굵게), 기존 밑줄 스타일. 그 아래 "사업자 등록 전 시범 운영 중입니다."
  - 질문 상세 답 칸 라벨 아래 `text-13` 안내 "이름·연락처 같은 개인정보는 적지 마세요."

- [ ] **Step 1: 실패하는 시험**

```tsx
describe('바닥글', () => {
  it('약관과 처리방침 링크를 보여 준다', () => {
    render(<Footer />);
    expect(screen.getByRole('link', { name: '이용약관' }).getAttribute('href')).toBe('/terms');
    expect(screen.getByRole('link', { name: '개인정보 처리방침' }).getAttribute('href')).toBe('/privacy');
    expect(document.body.textContent).toContain('사업자 등록 전 시범 운영');
  });
});
```

질문 안내는 `ClarifyingPanel`의 기존 시험이 있으면 거기에, 없으면 이 Task에서 `detailInput`이 있는 질문을 렌더해 문구를 확인하는 시험 하나를 더한다.

- [ ] **Step 2:** `npm test -- components/layout components/analysis-progress` → 실패
- [ ] **Step 3:** 구현
- [ ] **Step 4:** 같은 명령 통과
- [ ] **Step 5:** `git commit -m "feat: 바닥글 법적 안내 링크와 질문 답 개인정보 안내"`

### Task 9: 전체 점검과 문서

- [ ] **Step 1:** `backend/`: `ruff check .`, `ruff format --check .`, `mypy`, 전체 unittest. 실패는 `test_load_harness` 1건만 허용. 통과 개수를 `docs/TESTING.md` 측정 기준 문단에 날짜와 함께 고친다.
- [ ] **Step 2:** `frontend/`: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` 모두 통과.
- [ ] **Step 3:** E2E(`frontend`에서 `E2E_PYTHON=../backend/.venv/Scripts/python.exe npx playwright test`). 브라우저가 설치돼 있지 않아 못 돌리면 그 사실을 보고에 적는다.
- [ ] **Step 4:** 실험소 서버를 8001·3001로 띄워 `/privacy`·`/terms`·`/signup` 화면을 직접 열어 보고, 체크 없이 가입하면 막히고 체크하면 가입되는지 확인한다(동시 실행 시 환경 변수 `CORS_ALLOW_ORIGINS=http://localhost:3001`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`).
- [ ] **Step 5:** `git commit -m "docs: 시험 개수 갱신"`
