-- Initial schema for Postgres. The worker also calls init_db() at boot, so this
-- file is primarily a fallback for fast dev loops and a reference for Alembic
-- migrations to match. Keep the shape in sync with apps/worker/worker/db.py.

CREATE TABLE IF NOT EXISTS inference_records (
    id               BIGSERIAL PRIMARY KEY,
    event_id         VARCHAR(64)  UNIQUE NOT NULL,
    idempotency_key  VARCHAR(128) UNIQUE NOT NULL,
    model            VARCHAR(128) NOT NULL,
    provider         VARCHAR(64)  NOT NULL,
    event_timestamp  TIMESTAMPTZ  NOT NULL,
    latency_ms       INTEGER      NOT NULL,
    cost_usd         DOUBLE PRECISION NOT NULL,
    prompt_tokens    INTEGER      NOT NULL,
    completion_tokens INTEGER     NOT NULL,
    predicted_label  VARCHAR(128),
    expected_label   VARCHAR(128),
    s3_bucket        VARCHAR(256) NOT NULL,
    s3_key           VARCHAR(512) NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inference_model_ts
    ON inference_records (model, event_timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    event_id    VARCHAR(64)  NOT NULL,
    model       VARCHAR(128) NOT NULL,
    rule        VARCHAR(64)  NOT NULL,
    severity    VARCHAR(16)  NOT NULL,
    status      VARCHAR(16)  NOT NULL DEFAULT 'open',
    message     VARCHAR(1024) NOT NULL,
    evidence    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_model_ts ON alerts (model, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts (rule);

CREATE TABLE IF NOT EXISTS alert_events (
    id         BIGSERIAL PRIMARY KEY,
    alert_id   BIGINT      NOT NULL REFERENCES alerts(id),
    kind       VARCHAR(32) NOT NULL,
    note       VARCHAR(512) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alert_events_alert ON alert_events (alert_id);

CREATE TABLE IF NOT EXISTS partner_delivery_attempts (
    id                 BIGSERIAL PRIMARY KEY,
    alert_id           BIGINT      NOT NULL REFERENCES alerts(id),
    partner            VARCHAR(32) NOT NULL,
    partner_request_id VARCHAR(128) NOT NULL,
    attempt            INTEGER     NOT NULL,
    status             VARCHAR(16) NOT NULL,
    http_status        INTEGER,
    error              VARCHAR(512),
    latency_ms         INTEGER     NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_partner_alert ON partner_delivery_attempts (alert_id);

CREATE TABLE IF NOT EXISTS investigations (
    id                            BIGSERIAL PRIMARY KEY,
    alert_id                      BIGINT       NOT NULL,
    event_id                      VARCHAR(64)  NOT NULL,
    model                         VARCHAR(128) NOT NULL,
    rule                          VARCHAR(64)  NOT NULL,
    severity                      VARCHAR(16)  NOT NULL,
    root_cause                    TEXT         NOT NULL,
    root_cause_label              VARCHAR(64)  NOT NULL,
    confidence                    DOUBLE PRECISION NOT NULL,
    report_json                   JSONB        NOT NULL,
    tool_calls                    INTEGER      NOT NULL DEFAULT 0,
    verify_loops                  INTEGER      NOT NULL DEFAULT 0,
    cost_usd                      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    latency_ms                    INTEGER      NOT NULL DEFAULT 0,
    llm_backend                   VARCHAR(32)  NOT NULL,
    llm_model_id                  VARCHAR(128) NOT NULL,
    feedback_correct              BOOLEAN,
    feedback_correct_root_cause   VARCHAR(128),
    feedback_notes                TEXT,
    created_at                    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_investigations_alert ON investigations (alert_id);
CREATE INDEX IF NOT EXISTS idx_investigations_model_ts ON investigations (model, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_investigations_root_cause_label ON investigations (root_cause_label);
