-- 요청 실행 상태와 분석 상태는 별도로 관리합니다.
-- 보완 요청은 최종 결과가 없으므로 판단 결과와 분리합니다.
CREATE TABLE IF NOT EXISTS analysis_requests (
    request_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(request_id)) > 0),
    input_address TEXT NOT NULL CHECK (length(trim(input_address)) > 0),
    radius_m INTEGER CHECK (radius_m IS NULL OR (typeof(radius_m) = 'integer' AND radius_m > 0)),
    site_json TEXT CHECK (site_json IS NULL OR json_valid(site_json)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (
        (status IN ('pending', 'running') AND completed_at IS NULL
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
    CHECK (json_extract(event_json, '$.request_id') IS request_id),
    CHECK (json_extract(event_json, '$.request.agent_id') IS agent_id),
    CHECK (json_extract(event_json, '$.status') IS status)
);
