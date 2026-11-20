-- =============================================================================
-- akalin-browser-module - PostgreSQL Veritabanı Şeması (akalin_browser_db)
-- AI Ajanları için Hibrit Sanal Tarayıcı Oturumları, Snapshot ve Telemetri Şeması.
-- =============================================================================

CREATE TABLE IF NOT EXISTS browser_sessions (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(120) NOT NULL,
    app_id VARCHAR(64) NOT NULL DEFAULT '',
    agent_id VARCHAR(64) NOT NULL DEFAULT '',
    current_url TEXT NOT NULL DEFAULT '',
    current_title TEXT NOT NULL DEFAULT '',
    mode VARCHAR(16) NOT NULL DEFAULT 'http',
    status VARCHAR(32) NOT NULL DEFAULT 'idle',
    requests_served INT NOT NULL DEFAULT 0,
    proxy_endpoint VARCHAR(255) NOT NULL DEFAULT '',
    ttl_sec INT NOT NULL DEFAULT 300,
    created_at VARCHAR(64) NOT NULL,
    last_active_at VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_browser_sessions_conv_status
    ON browser_sessions(conversation_id, status);

CREATE INDEX IF NOT EXISTS idx_browser_sessions_last_active
    ON browser_sessions(last_active_at DESC);

CREATE TABLE IF NOT EXISTS session_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES browser_sessions(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    snapshot_text TEXT NOT NULL,
    interactive_elements_json TEXT NOT NULL DEFAULT '[]',
    created_at VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_snapshots_sess
    ON session_snapshots(session_id);

CREATE TABLE IF NOT EXISTS browser_metrics_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    timestamp_iso VARCHAR(64) NOT NULL,
    total_sessions INT NOT NULL DEFAULT 0,
    busy_sessions INT NOT NULL DEFAULT 0,
    idle_sessions INT NOT NULL DEFAULT 0,
    http_sessions INT NOT NULL DEFAULT 0,
    chromium_sessions INT NOT NULL DEFAULT 0,
    avg_render_ms INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_browser_metrics_ts
    ON browser_metrics_snapshots(timestamp_iso DESC);

CREATE TABLE IF NOT EXISTS browser_scaling_events (
    id VARCHAR(64) PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_browser_scaling_events_ts
    ON browser_scaling_events(created_at DESC);

CREATE TABLE IF NOT EXISTS browser_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL DEFAULT '{}',
    updated_at VARCHAR(64) NOT NULL DEFAULT ''
);
