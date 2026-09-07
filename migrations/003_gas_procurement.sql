CREATE TABLE IF NOT EXISTS gas_procurement_months (
    reporting_month DATE PRIMARY KEY,
    commodity_price_uah_per_1000m3 NUMERIC NOT NULL,
    distribution_price_uah_per_1000m3 NUMERIC NOT NULL,
    capacity_price_uah_per_1000m3 NUMERIC NOT NULL,
    total_price_uah_per_1000m3 NUMERIC NOT NULL,
    planned_volume_m3 NUMERIC NOT NULL,
    vat_included BOOLEAN NOT NULL,
    source_sheet TEXT NOT NULL,
    imported_at_utc TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS gas_consumption_days (
    delivery_date DATE PRIMARY KEY,
    planned_volume_m3 NUMERIC NOT NULL,
    actual_volume_m3 NUMERIC,
    source_sheet TEXT NOT NULL,
    imported_at_utc TIMESTAMPTZ NOT NULL
);
