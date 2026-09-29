CREATE TABLE IF NOT EXISTS gas_market_indices (
    series TEXT NOT NULL,
    quote_date DATE NOT NULL,
    delivery_date DATE NOT NULL,
    price NUMERIC NOT NULL CHECK (price > 0),
    currency TEXT NOT NULL,
    unit TEXT NOT NULL,
    vat TEXT NOT NULL,
    payment_terms TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    available_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (series, quote_date, delivery_date, payment_terms)
);

CREATE INDEX IF NOT EXISTS idx_gas_market_indices_delivery
    ON gas_market_indices (delivery_date, series);

COMMENT ON TABLE gas_market_indices IS
    'Source-native public gas-market indicators from validated UEEX/CEGH snapshots.';
