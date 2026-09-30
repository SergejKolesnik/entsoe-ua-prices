CREATE TABLE IF NOT EXISTS system_metrics (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    bidding_zone TEXT NOT NULL,
    category TEXT NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    value_mw NUMERIC NOT NULL,
    source_revision TEXT,
    raw_artifact_id BIGINT REFERENCES raw_artifacts(id),
    ingested_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source, metric, bidding_zone, category, observed_at_utc)
);

CREATE INDEX IF NOT EXISTS idx_system_metrics_time
    ON system_metrics (metric, bidding_zone, observed_at_utc);
