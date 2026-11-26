-- Jobs requested from the dashboard: a data update ('sync'), a backup ('export') or a
-- restore ('import'). The host agent runs them, because the API container has neither
-- the provider credentials, nor internet access, nor the raw provider captures.
CREATE TABLE IF NOT EXISTS core.agent_requests
(
    request_id UUID,
    kind LowCardinality(String),
    requested_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = MergeTree
ORDER BY (requested_at, request_id);

-- The agent's heartbeats and the outcome of each job. `detail` holds counts only.
CREATE TABLE IF NOT EXISTS metadata.agent_events
(
    request_id UUID,
    event LowCardinality(String),
    detail String,
    recorded_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = MergeTree
ORDER BY (recorded_at, request_id)
TTL toDateTime(recorded_at) + INTERVAL 7 DAY DELETE WHERE event = 'heartbeat';

-- Backup archives on their way between the browser and the agent, base64 encoded.
-- They hold private data, so they expire after a day.
CREATE TABLE IF NOT EXISTS core.agent_files
(
    request_id UUID,
    direction LowCardinality(String),
    data String,
    created_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = MergeTree
ORDER BY request_id
TTL toDateTime(created_at) + INTERVAL 1 DAY;
