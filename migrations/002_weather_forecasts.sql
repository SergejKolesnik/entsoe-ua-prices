CREATE TABLE IF NOT EXISTS weather_forecasts (
    source text NOT NULL,
    model text NOT NULL,
    location_id text NOT NULL,
    latitude numeric NOT NULL,
    longitude numeric NOT NULL,
    forecast_vintage_utc timestamptz NOT NULL,
    valid_start_utc timestamptz NOT NULL,
    temperature_c numeric NOT NULL,
    cloud_cover_percent numeric NOT NULL CHECK (cloud_cover_percent BETWEEN 0 AND 100),
    shortwave_radiation_wm2 numeric NOT NULL CHECK (shortwave_radiation_wm2 >= 0),
    wind_speed_100m_kmh numeric NOT NULL CHECK (wind_speed_100m_kmh >= 0),
    raw_artifact_id bigint NOT NULL REFERENCES raw_artifacts(id),
    ingested_at_utc timestamptz NOT NULL,
    PRIMARY KEY (source, model, location_id, forecast_vintage_utc, valid_start_utc)
);

CREATE INDEX IF NOT EXISTS idx_weather_forecasts_valid
ON weather_forecasts (valid_start_utc, forecast_vintage_utc);
