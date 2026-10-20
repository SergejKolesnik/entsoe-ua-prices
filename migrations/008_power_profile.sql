CREATE TABLE IF NOT EXISTS power_profile_observations (
    delivery_start_local TIMESTAMP PRIMARY KEY,
    delivery_date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour < 24),
    planned_purchase_mwh NUMERIC,
    purchased_mwh NUMERIC,
    gpu_mwh NUMERIC,
    ses_mwh NUMERIC,
    grid_export_mwh NUMERIC,
    technology_consumption_mwh NUMERIC,
    power_consumption_mwh NUMERIC,
    imbalance_mwh NUMERIC,
    source_sheet TEXT NOT NULL,
    imported_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_power_profile_delivery
    ON power_profile_observations (delivery_date);
