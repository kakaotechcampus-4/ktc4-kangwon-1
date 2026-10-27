-- 요청 실행 상태와 분석 상태는 별도로 관리합니다.
-- 보완 요청은 최종 결과가 없으므로 판단 결과와 분리합니다.
CREATE TABLE IF NOT EXISTS analysis_requests (
    request_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(request_id)) > 0),
    input_address TEXT NOT NULL CHECK (length(trim(input_address)) > 0),
    catalog_version TEXT,
    radius_m INTEGER CHECK (radius_m IS NULL OR (typeof(radius_m) = 'integer' AND radius_m > 0)),
    site_json TEXT CHECK (site_json IS NULL OR json_valid(site_json)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'waiting_for_input')),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (
        (status IN ('pending', 'running', 'waiting_for_input') AND completed_at IS NULL
            AND result_json IS NULL AND error_json IS NULL)
        OR (status = 'completed' AND completed_at IS NOT NULL
            AND result_json IS NOT NULL AND error_json IS NULL)
        OR (status = 'failed' AND completed_at IS NOT NULL
            AND error_json IS NOT NULL AND result_json IS NULL)
    ),
    CHECK (result_json IS NULL OR json_extract(result_json, '$.request_id') IS request_id)
);

CREATE TABLE IF NOT EXISTS decision_failures (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    failed_at TEXT NOT NULL,
    error_json TEXT NOT NULL CHECK (json_valid(error_json)),
    diagnostics_json TEXT NOT NULL CHECK (json_valid(diagnostics_json)),
    PRIMARY KEY (request_id, failed_at)
);

-- 진행 화면용 단계 이벤트입니다. 분석 판단의 근거가 아니며 요약만 저장합니다.
CREATE TABLE IF NOT EXISTS analysis_events (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    seq INTEGER NOT NULL CHECK (seq > 0),
    stage TEXT NOT NULL CHECK (length(stage) > 0),
    event TEXT NOT NULL CHECK (event IN ('started', 'completed', 'failed', 'waiting')),
    detail_json TEXT NOT NULL CHECK (json_valid(detail_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, seq)
);


-- 새 구조 PR2: 기존 테이블을 유지하며 요청당 원문 스냅샷 하나를 추가합니다.
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL UNIQUE REFERENCES analysis_requests(request_id),
    run_id TEXT NOT NULL,
    base_source_manifest TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(base_source_manifest)),
    completeness TEXT NOT NULL CHECK (completeness IN ('collecting','complete','partial')),
    source_periods TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(source_periods)),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_payloads (
    payload_hash TEXT PRIMARY KEY NOT NULL,
    response_json TEXT NOT NULL CHECK (json_valid(response_json))
);
CREATE TABLE IF NOT EXISTS raw_responses (
    response_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    source TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('api','file','user')),
    request_args_json TEXT NOT NULL CHECK (json_valid(request_args_json)),
    page TEXT NOT NULL,
    http_status INTEGER,
    collected_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL REFERENCES raw_payloads(payload_hash),
    group_key TEXT NOT NULL,
    expected_rows INTEGER,
    duplicate_of TEXT REFERENCES raw_responses(response_id),
    FOREIGN KEY (request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS snapshot_request_pair ON snapshots(request_id,snapshot_id);
CREATE INDEX IF NOT EXISTS raw_response_page ON raw_responses(snapshot_id,run_id,source,group_key,page);
CREATE TABLE IF NOT EXISTS raw_rows (
    raw_row_id TEXT PRIMARY KEY NOT NULL,
    payload_hash TEXT NOT NULL REFERENCES raw_payloads(payload_hash),
    row_index INTEGER NOT NULL,
    natural_key TEXT,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json)),
    row_hash TEXT NOT NULL,
    UNIQUE(payload_hash,row_index)
);
CREATE INDEX IF NOT EXISTS raw_row_hash ON raw_rows(row_hash);
CREATE TABLE IF NOT EXISTS raw_response_rows (
    response_id TEXT NOT NULL REFERENCES raw_responses(response_id),
    raw_row_id TEXT NOT NULL REFERENCES raw_rows(raw_row_id),
    duplicate_of TEXT REFERENCES raw_rows(raw_row_id),
    PRIMARY KEY(response_id,raw_row_id)
);
CREATE INDEX IF NOT EXISTS raw_response_row_ref ON raw_response_rows(raw_row_id);

-- 실행기가 바인딩하는 함수가 없거나 범위를 지정하지 않으면 행을 노출하지 않습니다.
CREATE VIEW IF NOT EXISTS v_raw_stores AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.bizesId') AS store_id,
       json_extract(r.raw_json,'$.indsMclsCd') AS middle_code,
       json_extract(r.raw_json,'$.indsSclsCd') AS small_code,
       json_extract(r.raw_json,'$.lat') AS latitude,
       json_extract(r.raw_json,'$.lon') AS longitude
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='commercial_area' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_lifecycle AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code,
       json_extract(r.raw_json,'$.SVC_INDUTY_CD') AS seoul_industry_code,
       json_extract(r.raw_json,'$.SIMILR_INDUTY_STOR_CO') AS store_count,
       json_extract(r.raw_json,'$.OPBIZ_STOR_CO') AS opening_count,
       json_extract(r.raw_json,'$.CLSBIZ_STOR_CO') AS closing_count
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='business_lifecycle' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_floating AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='floating_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_resident AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='resident_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_worker AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='worker_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();

CREATE INDEX IF NOT EXISTS raw_row_natural_key ON raw_rows(natural_key);

CREATE VIEW IF NOT EXISTS v_raw_map AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.place_name') AS name,
       json_extract(r.raw_json,'$.category_name') AS kakao_category,
       json_extract(r.raw_json,'$.distance') AS distance_m
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='map' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_regulation AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.snapshot_id,r.raw_json
FROM raw_rows r JOIN raw_response_rows e USING(raw_row_id) JOIN raw_responses p USING(response_id)
WHERE p.source='regulation' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();


-- PR3 사실·코드 점수는 불변 레코드로 보존합니다.
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    industry_code TEXT,
    source TEXT NOT NULL,
    metric TEXT NOT NULL CHECK(metric IN ('raw_cell','by_time','time_per_hour_share','covered_trade_areas','period_code','mean_daily_per_trade_area','pattern_fit_index','pattern_scale_percentile','pattern_daily_per_trade_area','weekend_index','day_fit_index','age_share','resident_age_share','worker_age_share','target_age_index','yoy_change','density_per_km2','competition_index','seoul_median_density','daily_total_median','distance_m','facility_distance_ratio','recent_year_close_rate','oldest_year_close_rate','net_change_rate','turnover_rate','close_rate_ratio','net_change_index','turnover_ratio','close_trend_ratio','store_exposure','avg_store_count','zero_filled_sources','seoul_close_rate','seoul_turnover_rate','seoul_net_change_rate','seoul_close_trend_ratio','store_count','opening_count','closing_count','lq','differentiation','place_name','kakao_category','match_status','regulation_status','zone_contains','floor','exclusive_area','space_condition','existing_facilities','industry_preferences','space_requirements','space_fit')),
    value_json TEXT NOT NULL CHECK(json_valid(value_json)),
    unit TEXT NOT NULL,
    period TEXT NOT NULL,
    spatial_scope_json TEXT NOT NULL CHECK(json_valid(spatial_scope_json)),
    comparison_json TEXT NOT NULL CHECK(json_valid(comparison_json)),
    status TEXT NOT NULL CHECK(status IN ('observed','unknown','n.a.')),
    citable INTEGER NOT NULL CHECK(citable IN (0,1)),
    calc_version TEXT NOT NULL,
    lineage_hash TEXT NOT NULL,
    identity_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK((status='observed' AND json_type(value_json) != 'null') OR
          (status!='observed' AND json_type(value_json)='null' AND citable=0) OR
          (metric='space_fit' AND status='unknown' AND json_type(value_json)='object' AND citable=0)),
    UNIQUE(snapshot_id,identity_hash),
    FOREIGN KEY(request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE TABLE IF NOT EXISTS fact_sources (
    fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    raw_row_id TEXT NOT NULL REFERENCES raw_rows(raw_row_id),
    field_pointer TEXT NOT NULL,
    PRIMARY KEY(fact_id,raw_row_id,field_pointer)
);
-- 원문 근거는 그대로 두고 파생 사실의 부모 계보와 현재 공간 비교만 추가합니다.
CREATE TABLE IF NOT EXISTS fact_parents (
    fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    parent_fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    PRIMARY KEY(fact_id,parent_fact_id),
    CHECK(fact_id != parent_fact_id)
);
CREATE INDEX IF NOT EXISTS idx_fact_parents_parent ON fact_parents(parent_fact_id);
CREATE TRIGGER IF NOT EXISTS fact_parents_scope BEFORE INSERT ON fact_parents
WHEN NOT EXISTS (
    SELECT 1 FROM facts child JOIN facts parent ON parent.fact_id=NEW.parent_fact_id
    WHERE child.fact_id=NEW.fact_id AND child.request_id=parent.request_id
    AND child.snapshot_id=parent.snapshot_id
    AND (parent.industry_code IS NULL OR parent.industry_code=child.industry_code)
    AND (child.status!='observed' OR (parent.status='observed' AND parent.citable=1))
    AND EXISTS (
        SELECT 1 FROM json_each(child.comparison_json,'$.parent_fact_ids')
        WHERE value=NEW.parent_fact_id
    )
)
BEGIN SELECT RAISE(ABORT,'parent fact scope differs'); END;
CREATE TRIGGER IF NOT EXISTS immutable_fact_parents BEFORE UPDATE ON fact_parents
BEGIN SELECT RAISE(ABORT,'fact_parents are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_fact_parents_delete BEFORE DELETE ON fact_parents
BEGIN SELECT RAISE(ABORT,'fact_parents are immutable'); END;

CREATE TABLE IF NOT EXISTS space_fit_current (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    industry_code TEXT NOT NULL,
    fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    PRIMARY KEY(request_id,snapshot_id,industry_code),
    FOREIGN KEY(request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE TRIGGER IF NOT EXISTS space_fit_current_scope BEFORE INSERT ON space_fit_current
WHEN NOT EXISTS (
    SELECT 1 FROM facts WHERE fact_id=NEW.fact_id AND request_id=NEW.request_id
    AND snapshot_id=NEW.snapshot_id AND industry_code=NEW.industry_code
    AND source='industry_profile' AND metric='space_fit'
)
BEGIN SELECT RAISE(ABORT,'space fit scope differs'); END;
CREATE TRIGGER IF NOT EXISTS space_fit_current_update_scope BEFORE UPDATE ON space_fit_current
WHEN NOT EXISTS (
    SELECT 1 FROM facts WHERE fact_id=NEW.fact_id AND request_id=NEW.request_id
    AND snapshot_id=NEW.snapshot_id AND industry_code=NEW.industry_code
    AND source='industry_profile' AND metric='space_fit'
)
BEGIN SELECT RAISE(ABORT,'space fit scope differs'); END;

CREATE TABLE IF NOT EXISTS score_snapshots (
    score_snapshot_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    run_id TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    summary_json TEXT NOT NULL CHECK(json_valid(summary_json)),
    top5_json TEXT NOT NULL CHECK(json_valid(top5_json)),
    L_review_state TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TEXT NOT NULL,
    FOREIGN KEY(request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE TABLE IF NOT EXISTS scores (
    score_snapshot_id TEXT NOT NULL REFERENCES score_snapshots(score_snapshot_id),
    industry_code TEXT NOT NULL,
    item TEXT NOT NULL CHECK(item IN ('D1','D2','D3','D4','C1','C4','S1','S2','S3','S4','L')),
    weight REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('observed','unknown','n.a.')),
    grade INTEGER CHECK(grade BETWEEN 0 AND 4),
    points REAL,
    fact_ids_json TEXT NOT NULL CHECK(json_valid(fact_ids_json)),
    PRIMARY KEY(score_snapshot_id,industry_code,item),
    CHECK((status='observed' AND grade IS NOT NULL AND points IS NOT NULL) OR (status!='observed' AND grade IS NULL AND points IS NULL))
);
CREATE TRIGGER IF NOT EXISTS immutable_facts BEFORE UPDATE ON facts
BEGIN SELECT RAISE(ABORT,'facts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_facts_delete BEFORE DELETE ON facts
BEGIN SELECT RAISE(ABORT,'facts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_fact_sources BEFORE UPDATE ON fact_sources
BEGIN SELECT RAISE(ABORT,'fact_sources are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_fact_sources_delete BEFORE DELETE ON fact_sources
BEGIN SELECT RAISE(ABORT,'fact_sources are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_scores BEFORE UPDATE ON scores
BEGIN SELECT RAISE(ABORT,'scores are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_scores_delete BEFORE DELETE ON scores
BEGIN SELECT RAISE(ABORT,'scores are immutable'); END;
CREATE INDEX IF NOT EXISTS idx_score_snapshots_req ON score_snapshots(request_id,snapshot_id,created_at);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    run_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input_json TEXT NOT NULL CHECK(json_valid(input_json)),
    reply_json TEXT NOT NULL CHECK(json_valid(reply_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY(request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);

CREATE TABLE IF NOT EXISTS agentic_runs (
    request_id TEXT PRIMARY KEY REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','draft_available','waiting_for_input','completed','failed')),
    state_json TEXT NOT NULL CHECK(json_valid(state_json)),
    result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agentic_reports (
    report_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    proposal_json TEXT NOT NULL CHECK(json_valid(proposal_json)),
    result_json TEXT NOT NULL CHECK(json_valid(result_json)),
    rendered_json TEXT NOT NULL CHECK(json_valid(rendered_json)),
    phase TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisor_consults (
    consult_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    question TEXT NOT NULL,
    fact_ids_json TEXT NOT NULL CHECK(json_valid(fact_ids_json)),
    model TEXT,
    family TEXT NOT NULL,
    usage_json TEXT NOT NULL CHECK(json_valid(usage_json)),
    answer_json TEXT NOT NULL CHECK(json_valid(answer_json)),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agentic_questions (
    question_session_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    questions_json TEXT NOT NULL CHECK(json_valid(questions_json)),
    answers_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(answers_json)),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agentic_reviews (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    actor TEXT NOT NULL,
    review_json TEXT NOT NULL CHECK(json_valid(review_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY(request_id,snapshot_id,actor)
);
-- LD3: 분기 자료는 요청에 복사하지 않고 고정 버전과 조회 레시피만 저장합니다.
CREATE TABLE IF NOT EXISTS local_snapshots (
    snapshot_id TEXT PRIMARY KEY REFERENCES snapshots(snapshot_id),
    database_path TEXT NOT NULL, versions_json TEXT NOT NULL,
    config_hashes_json TEXT NOT NULL, scope_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_provenance (
    provenance_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    source TEXT NOT NULL, version_ids_json TEXT NOT NULL,
    query_json TEXT NOT NULL, calc_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_fact_lineage (
    fact_id TEXT PRIMARY KEY REFERENCES facts(fact_id),
    provenance_id TEXT NOT NULL REFERENCES local_provenance(provenance_id),
    row_key TEXT, column_name TEXT
);
CREATE TRIGGER IF NOT EXISTS immutable_local_fact_lineage BEFORE UPDATE ON local_fact_lineage
BEGIN SELECT RAISE(ABORT,'local_fact_lineage are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_local_fact_lineage_delete BEFORE DELETE ON local_fact_lineage
BEGIN SELECT RAISE(ABORT,'local_fact_lineage are immutable'); END;
CREATE INDEX IF NOT EXISTS idx_tool_calls_req ON tool_calls(request_id,snapshot_id,actor,tool_name);
CREATE INDEX IF NOT EXISTS idx_advisor_consults_req ON advisor_consults(request_id,snapshot_id);
CREATE TABLE IF NOT EXISTS fact_aliases (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    alias TEXT NOT NULL CHECK(length(alias)=8),
    fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    PRIMARY KEY(request_id,alias), UNIQUE(request_id,fact_id)
);
CREATE TRIGGER IF NOT EXISTS scoped_fact_alias BEFORE INSERT ON fact_aliases
WHEN NOT EXISTS(SELECT 1 FROM facts f WHERE f.fact_id=NEW.fact_id AND f.request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT,'fact alias scope mismatch'); END;
CREATE TRIGGER IF NOT EXISTS immutable_fact_alias BEFORE UPDATE ON fact_aliases
BEGIN SELECT RAISE(ABORT,'fact aliases are immutable'); END;

-- ── 인증 ────────────────────────────────────────────────────────────────
-- 계정(users)과 로그인 수단(user_identities)을 나눕니다. 한 테이블에 합치면
-- 이메일로 가입한 사람이 나중에 카카오로 들어올 때 계정이 둘로 갈립니다.
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY NOT NULL,
    email TEXT UNIQUE,                -- 소셜만 쓰는 계정은 없을 수 있습니다(SQLite는 NULL 중복 허용)
    password_hash TEXT,               -- 소셜만 쓰는 계정은 NULL
    email_verified_at TEXT,
    display_name TEXT,
    profile_image_url TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL,
    CHECK (password_hash IS NULL OR email IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS user_identities (
    provider TEXT NOT NULL CHECK (provider IN ('kakao')),
    provider_user_id TEXT NOT NULL,   -- 카카오 id는 int64라 TEXT로 보관합니다
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX IF NOT EXISTS idx_user_identities_user ON user_identities(user_id);

-- 쿠키로 나가는 토큰은 보관하지 않고 sha256 해시만 둡니다.
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id, expires_at);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY NOT NULL,
    next_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- 가입 인증과 비밀번호 재설정이 같은 모양이라 한 표로 씁니다.
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    purpose TEXT NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id, purpose);

-- 무차별 대입 방어. 성공도 남겨 운영 중 이상 징후를 봅니다.
CREATE TABLE IF NOT EXISTS login_attempts (
    email TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(email, attempted_at);

-- 소유자는 analysis_requests에 칼럼으로 넣지 않습니다. detail()이 SELECT *를
-- 그대로 응답 본문으로 내보내고 있어, 칼럼을 더하면 user_id가 외부에 노출됩니다.
CREATE TABLE IF NOT EXISTS analysis_owners (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analysis_owners_user ON analysis_owners(user_id, created_at DESC);
