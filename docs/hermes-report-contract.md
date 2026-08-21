# Hermes daily report contract

## Transport and trust boundary

The producer reads Neon or SQLite through `SQLiteMarketRepository`'s read methods,
serializes a fixed document, and publishes only that document. Hermes receives no
database role, connection string, SQL interface, source token, or Streamlit session.

`schema_version` is currently `1.0`. Consumers must fail closed on an unsupported
major version. The static export is public because every included observation comes
from public market, central-bank, weather, or project forecast data. GitHub hosts the
file and supplies its normal CDN and anti-abuse limits. One fetch per report run is
the intended usage.

## Top-level fields

- `generated_at`: UTC production timestamp.
- `delivery_date`: Kyiv market delivery date.
- `timezone`: always `Europe/Kyiv` for version 1.
- `status`: `complete`, `incomplete`, `unavailable`, or `stale`.
- `source_provenance`: sanitized source identity and collection freshness; never raw errors.
- `semantics`: currency, units, VAT posture, and null policy.
- `quality`: expected, actual, and validated period counts. Expected count is derived
  from Kyiv midnight boundaries and is therefore 23, 24, or 25.
- `summary`: daily price/volume and prior-day/trailing-seven-day comparisons.
- `hourly`: ordered Ukrainian DAM intervals with UTC and offset-aware Kyiv timestamps.
- `context`: independently status-labelled FX, neighbor prices, border flows, regional
  weather, and frozen baseline forecast data.

## Consumer rules

1. Parse numbers as numbers and preserve `null` as unavailable.
2. Never infer missing periods, volumes, context, or VAT treatment.
3. Use headline statements only when top-level `status` is `complete`.
4. Mention a context dataset only when its own status is `complete` or explicitly
   qualify `partial`/`incomplete` evidence.
5. Verify `delivery_date` against the requested report date and reject an unexpected
   `schema_version`.
6. Cache the successful response for the duration of one report build; do not poll.

The producer intentionally declares VAT as `not_asserted_by_source_contract` until
an authoritative source contract is recorded in the project. This avoids silently
misstating whether a displayed price includes VAT.
