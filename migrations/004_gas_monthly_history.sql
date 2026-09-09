CREATE TABLE IF NOT EXISTS gas_monthly_history (
    reporting_month DATE PRIMARY KEY CHECK (EXTRACT(DAY FROM reporting_month) = 1),
    commodity_price NUMERIC NOT NULL CHECK (commodity_price >= 0),
    transportation_price NUMERIC NOT NULL CHECK (transportation_price >= 0),
    distribution_price NUMERIC NOT NULL CHECK (distribution_price >= 0),
    total_price NUMERIC NOT NULL CHECK (total_price >= 0),
    plant_volume_m3 NUMERIC NOT NULL CHECK (plant_volume_m3 >= 0),
    sanatorium_volume_m3 NUMERIC NOT NULL CHECK (sanatorium_volume_m3 >= 0),
    total_volume_m3 NUMERIC NOT NULL CHECK (total_volume_m3 = plant_volume_m3 + sanatorium_volume_m3),
    amount_uah NUMERIC NOT NULL CHECK (amount_uah >= 0),
    vat_included BOOLEAN NOT NULL CHECK (vat_included),
    source_url TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    imported_at_utc TIMESTAMPTZ NOT NULL
);
