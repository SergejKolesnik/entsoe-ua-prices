ALTER TABLE gas_monthly_history
    ADD COLUMN IF NOT EXISTS commodity_price_excluding_vat NUMERIC;

COMMENT ON COLUMN gas_monthly_history.commodity_price_excluding_vat IS
    'Verified annual-sheet commodity price without VAT; populated only from an explicit source column.';
