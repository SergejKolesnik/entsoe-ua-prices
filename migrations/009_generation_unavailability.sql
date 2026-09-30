CREATE TABLE IF NOT EXISTS generation_unavailability (
    source TEXT NOT NULL,
    event_id TEXT NOT NULL,
    bidding_zone TEXT NOT NULL,
    unit_name TEXT,
    business_type TEXT,
    available_capacity_mw NUMERIC,
    start_utc TIMESTAMPTZ,
    end_utc TIMESTAMPTZ,
    raw_artifact_id INTEGER,
    ingested_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source, event_id)
);

CREATE INDEX IF NOT EXISTS idx_generation_unavailability_period
    ON generation_unavailability (start_utc, end_utc, bidding_zone);
