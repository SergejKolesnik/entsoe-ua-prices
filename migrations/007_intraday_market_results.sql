CREATE TABLE IF NOT EXISTS intraday_market_results (
    id BIGSERIAL PRIMARY KEY,
    delivery_start_utc TIMESTAMPTZ NOT NULL,
    delivery_end_utc TIMESTAMPTZ NOT NULL,
    settlement_period INTEGER NOT NULL CHECK (settlement_period > 0),
    weighted_price_uah_per_mwh NUMERIC NOT NULL CHECK (weighted_price_uah_per_mwh >= 0),
    minimum_price_uah_per_mwh NUMERIC NOT NULL CHECK (minimum_price_uah_per_mwh >= 0),
    maximum_price_uah_per_mwh NUMERIC NOT NULL CHECK (maximum_price_uah_per_mwh >= minimum_price_uah_per_mwh),
    last_price_uah_per_mwh NUMERIC NOT NULL CHECK (
        last_price_uah_per_mwh >= minimum_price_uah_per_mwh
        AND last_price_uah_per_mwh <= maximum_price_uah_per_mwh
    ),
    sale_volume_mwh NUMERIC NOT NULL CHECK (sale_volume_mwh >= 0),
    purchase_volume_mwh NUMERIC NOT NULL CHECK (purchase_volume_mwh >= 0),
    declared_sale_volume_mwh NUMERIC NOT NULL CHECK (declared_sale_volume_mwh >= 0),
    declared_purchase_volume_mwh NUMERIC NOT NULL CHECK (declared_purchase_volume_mwh >= 0),
    source TEXT NOT NULL,
    raw_artifact_id BIGINT NOT NULL REFERENCES raw_artifacts(id),
    ingested_at_utc TIMESTAMPTZ NOT NULL,
    UNIQUE (source, delivery_start_utc),
    CHECK (delivery_end_utc = delivery_start_utc + INTERVAL '1 hour'),
    CHECK (weighted_price_uah_per_mwh >= minimum_price_uah_per_mwh
           AND weighted_price_uah_per_mwh <= maximum_price_uah_per_mwh),
    CHECK (sale_volume_mwh = purchase_volume_mwh)
);

CREATE INDEX IF NOT EXISTS idx_intraday_market_results_delivery
ON intraday_market_results (delivery_start_utc);
