CREATE TABLE IF NOT EXISTS gas_price_history (
    reporting_month DATE PRIMARY KEY CHECK (EXTRACT(DAY FROM reporting_month) = 1),
    commodity_price NUMERIC NOT NULL CHECK (commodity_price >= 0),
    distribution_price NUMERIC NOT NULL CHECK (distribution_price >= 0),
    capacity_price NUMERIC NOT NULL CHECK (capacity_price >= 0),
    total_price NUMERIC NOT NULL CHECK (total_price >= 0),
    source_url TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    imported_at_utc TIMESTAMPTZ NOT NULL,
    CHECK (ABS(total_price - commodity_price - distribution_price - capacity_price) <= 0.02)
);

COMMENT ON TABLE gas_price_history IS
    'Historical VAT-exclusive gas prices with no implied plan or daily consumption.';
