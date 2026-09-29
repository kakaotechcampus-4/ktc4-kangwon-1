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
    round INTEGER NOT NULL CHECK (typeof(round) = 'integer' AND round BETWEEN 1 AND 2),
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
