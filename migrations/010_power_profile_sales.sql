-- Extend the isolated power-profile import with hourly sale plan/fact fields.
ALTER TABLE power_profile_observations
    ADD COLUMN IF NOT EXISTS planned_sale_mwh NUMERIC;
ALTER TABLE power_profile_observations
    ADD COLUMN IF NOT EXISTS sold_mwh NUMERIC;
ALTER TABLE power_profile_observations
    ADD COLUMN IF NOT EXISTS sale_imbalance_mwh NUMERIC;
