-- 요청 실행 상태와 분석 상태는 별도로 관리합니다.
-- 보완 요청은 최종 결과가 없으므로 판단 결과와 분리합니다.
CREATE TABLE IF NOT EXISTS analysis_requests (
    request_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(request_id)) > 0),
    input_address TEXT NOT NULL CHECK (length(trim(input_address)) > 0),
    catalog_version TEXT,
    analysis_mode TEXT NOT NULL DEFAULT 'single_decision' CHECK (analysis_mode IN ('single_decision', 'multi_agent')),
    execution_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(execution_json) AND json_type(execution_json) = 'object'),
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

CREATE TABLE IF NOT EXISTS decision_results (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    attempt INTEGER NOT NULL CHECK (typeof(attempt) = 'integer' AND attempt >= 1),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    source_attempts_json TEXT NOT NULL CHECK (
        json_valid(source_attempts_json) AND json_type(source_attempts_json) = 'object'
    ),
    supplement_request_json TEXT CHECK (
        supplement_request_json IS NULL OR json_valid(supplement_request_json)
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, attempt),
    CHECK (json_extract(result_json, '$.request_id') IS request_id),
    CHECK (json_extract(result_json, '$.agent_id') IS 'decision')
);

CREATE TABLE IF NOT EXISTS agent_results (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    agent_id TEXT NOT NULL CHECK (
        agent_id IN ('floating_population', 'business_lifecycle', 'commercial_area')
    ),
    attempt INTEGER NOT NULL CHECK (typeof(attempt) = 'integer' AND attempt >= 1),
    status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'no_data', 'error')),
    analysis_json TEXT NOT NULL CHECK (json_valid(analysis_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, agent_id, attempt),
    CHECK (json_extract(analysis_json, '$.request_id') IS request_id),
    CHECK (json_extract(analysis_json, '$.agent_id') IS agent_id),
    CHECK (json_extract(analysis_json, '$.status') IS status)
);

CREATE TABLE IF NOT EXISTS supplement_events (
    id INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    agent_id TEXT NOT NULL CHECK (agent_id IN ('floating_population', 'business_lifecycle', 'commercial_area')),
    status TEXT NOT NULL CHECK (status IN ('requested', 'succeeded', 'failed', 'rejected')),
    event_json TEXT NOT NULL CHECK (json_valid(event_json)),
    created_at TEXT NOT NULL,
    analysis_attempt INTEGER CHECK (analysis_attempt IS NULL OR (typeof(analysis_attempt) = 'integer' AND analysis_attempt >= 2)),
    CHECK (json_extract(event_json, '$.request_id') IS request_id),
    CHECK (json_extract(event_json, '$.request.agent_id') IS agent_id),
    CHECK (json_extract(event_json, '$.status') IS status)
);

CREATE TABLE IF NOT EXISTS map_observations (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    attempt INTEGER NOT NULL CHECK (typeof(attempt) = 'integer' AND attempt >= 1),
    adopted INTEGER NOT NULL DEFAULT 0 CHECK (adopted IN (0, 1)),
    plan_json TEXT NOT NULL CHECK (json_valid(plan_json)),
    task_json TEXT NOT NULL CHECK (json_valid(task_json)),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed')),
    observation_json TEXT CHECK (observation_json IS NULL OR json_valid(observation_json)),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (request_id, attempt),
    CHECK (json_extract(task_json, '$.request_id') IS request_id),
    CHECK (observation_json IS NULL OR json_extract(observation_json, '$.request_id') IS request_id),
    CHECK ((status = 'running' AND observation_json IS NULL AND completed_at IS NULL)
        OR (status = 'completed' AND observation_json IS NOT NULL AND completed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS agent_briefs (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    agent_id TEXT NOT NULL CHECK (agent_id IN ('floating_population','business_lifecycle','commercial_area')),
    brief_json TEXT NOT NULL CHECK (json_valid(brief_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, agent_id),
    CHECK (json_extract(brief_json, '$.request_id') IS request_id),
    CHECK (json_extract(brief_json, '$.agent_id') IS agent_id)
);

CREATE TABLE IF NOT EXISTS specialist_consults (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    round INTEGER NOT NULL CHECK (typeof(round) = 'integer' AND round BETWEEN 1 AND 6),
    agent_id TEXT NOT NULL CHECK (agent_id IN ('floating_population','business_lifecycle','commercial_area','map_analysis')),
    status TEXT NOT NULL CHECK (status IN ('answered','partial','unavailable')),
    answer_json TEXT NOT NULL CHECK (json_valid(answer_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, round, agent_id),
    CHECK (json_extract(answer_json, '$.request_id') IS request_id),
    CHECK (json_extract(answer_json, '$.round') IS round),
    CHECK (json_extract(answer_json, '$.query.agent_id') IS agent_id),
    CHECK (json_extract(answer_json, '$.status') IS status)
);

CREATE TABLE IF NOT EXISTS evaluation_drafts (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    draft_json TEXT NOT NULL CHECK (json_valid(draft_json)),
    created_at TEXT NOT NULL,
    CHECK (json_extract(draft_json, '$.request_id') IS request_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    evaluator_id TEXT NOT NULL CHECK (evaluator_id IN ('examiner','founder','customer','landlord_advocate')),
    source TEXT NOT NULL CHECK (source IN ('model','failed')),
    evaluation_json TEXT NOT NULL CHECK (json_valid(evaluation_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, evaluator_id),
    CHECK (json_extract(evaluation_json, '$.request_id') IS request_id),
    CHECK (json_extract(evaluation_json, '$.evaluator') IS evaluator_id),
    CHECK (json_extract(evaluation_json, '$.source') IS source)
);

CREATE TABLE IF NOT EXISTS evaluation_logs (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    log_json TEXT NOT NULL CHECK (json_valid(log_json) AND json_type(log_json) = 'array'),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_failures (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    failed_at TEXT NOT NULL,
    error_json TEXT NOT NULL CHECK (json_valid(error_json)),
    diagnostics_json TEXT NOT NULL CHECK (json_valid(diagnostics_json)),
    PRIMARY KEY (request_id, failed_at)
);

CREATE TABLE IF NOT EXISTS question_sessions (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    question_set_id TEXT NOT NULL UNIQUE CHECK (length(trim(question_set_id)) > 0),
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    answers_json TEXT CHECK (answers_json IS NULL OR json_valid(answers_json)),
    created_at TEXT NOT NULL,
    answered_at TEXT,
    CHECK ((answers_json IS NULL) = (answered_at IS NULL)),
    CHECK (json_extract(snapshot_json, '$.task.request_id') IS request_id),
    CHECK (json_extract(snapshot_json, '$.waiting.request_id') IS request_id),
    CHECK (json_extract(snapshot_json, '$.waiting.question_set_id') IS question_set_id),
    CHECK (answers_json IS NULL OR (
        json_extract(answers_json, '$.request_id') IS request_id
        AND json_extract(answers_json, '$.question_set_id') IS question_set_id
    ))
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

-- 요청별 보완 이력을 반복 조회하는 상세 화면을 위한 인덱스입니다.
CREATE INDEX IF NOT EXISTS idx_supplement_events_request_id ON supplement_events(request_id);


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
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    collected_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    group_key TEXT NOT NULL,
    expected_rows INTEGER,
    duplicate_of TEXT REFERENCES raw_responses(response_id),
    FOREIGN KEY (request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS snapshot_request_pair ON snapshots(request_id,snapshot_id);
CREATE INDEX IF NOT EXISTS raw_response_page ON raw_responses(snapshot_id,run_id,source,group_key,page);
CREATE TABLE IF NOT EXISTS raw_rows (
    raw_row_id TEXT PRIMARY KEY NOT NULL,
    response_id TEXT NOT NULL REFERENCES raw_responses(response_id),
    row_index INTEGER NOT NULL,
    natural_key TEXT,
    raw_json TEXT NOT NULL CHECK (json_valid(raw_json)),
    duplicate_of TEXT REFERENCES raw_rows(raw_row_id),
    UNIQUE(response_id,row_index)
);

-- 실행기가 바인딩하는 함수가 없거나 범위를 지정하지 않으면 행을 노출하지 않습니다.
CREATE VIEW IF NOT EXISTS v_raw_stores AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.bizesId') AS store_id,
       json_extract(r.raw_json,'$.indsMclsCd') AS middle_code,
       json_extract(r.raw_json,'$.indsSclsCd') AS small_code,
       json_extract(r.raw_json,'$.lat') AS latitude,
       json_extract(r.raw_json,'$.lon') AS longitude
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='commercial_area' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_lifecycle AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code,
       json_extract(r.raw_json,'$.SVC_INDUTY_CD') AS seoul_industry_code,
       json_extract(r.raw_json,'$.SIMILR_INDUTY_STOR_CO') AS store_count,
       json_extract(r.raw_json,'$.OPBIZ_STOR_CO') AS opening_count,
       json_extract(r.raw_json,'$.CLSBIZ_STOR_CO') AS closing_count
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='business_lifecycle' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_floating AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='floating_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_resident AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='resident_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_worker AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.run_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.STDR_YYQU_CD') AS quarter,
       json_extract(r.raw_json,'$.TRDAR_CD') AS trade_area_code
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='worker_population' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();

CREATE INDEX IF NOT EXISTS raw_row_natural_key ON raw_rows(natural_key);

CREATE VIEW IF NOT EXISTS v_raw_map AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.snapshot_id,r.raw_json,
       json_extract(r.raw_json,'$.place_name') AS name,
       json_extract(r.raw_json,'$.category_name') AS kakao_category,
       json_extract(r.raw_json,'$.distance') AS distance_m
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='map' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();
CREATE VIEW IF NOT EXISTS v_raw_regulation AS
SELECT r.raw_row_id,p.response_id,p.request_id,p.snapshot_id,r.raw_json
FROM raw_rows r JOIN raw_responses p USING(response_id)
WHERE p.source='regulation' AND p.request_id=raw_request_id() AND p.snapshot_id=raw_snapshot_id();


-- PR3 사실·코드 점수는 불변 레코드로 보존합니다.
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    industry_code TEXT,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
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
    CHECK((status='observed' AND json_type(value_json) != 'null') OR (status!='observed' AND json_type(value_json)='null' AND citable=0)),
    UNIQUE(snapshot_id,identity_hash),
    FOREIGN KEY(request_id,snapshot_id) REFERENCES snapshots(request_id,snapshot_id)
);
CREATE TABLE IF NOT EXISTS fact_sources (
    fact_id TEXT NOT NULL REFERENCES facts(fact_id),
    raw_row_id TEXT NOT NULL REFERENCES raw_rows(raw_row_id),
    field_pointer TEXT NOT NULL,
    PRIMARY KEY(fact_id,raw_row_id,field_pointer)
);
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
    item TEXT NOT NULL,
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
    status TEXT NOT NULL,
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
