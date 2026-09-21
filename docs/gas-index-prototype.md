# CEGHIX + UEEX isolated import prototype

## Scope and evidence

This experiment is independent of the running collectors, internal procurement
import, Streamlit, migrations and database adapters. It has no SQL or Neon write
path, no scheduler and no production CLI registration. No new dependency is needed.

The original experiment was recovered onto current `main` at `1d90bbc` and
extended on `codex/ueex-gas-factors-dry-run`. Only its isolated source, parser,
domain, validation and dry-run modules were reused; the old branch itself was
not merged because it predates later application work.

Official source references:

- [CEGH direct downloads](https://www.cegh.at/en/direct-download-links/):
  the Austria Day Ahead CSV export is used, with its exact eleven-column header.
- [UEEX monthly resource prices](https://www.ueex.com.ua/exchange-quotations/natural-gas/medium-and-long-term-market/):
  the unique `weighted` table, UAH spans, payment-column labels, snapshot date
  and VAT-regime notice are checked.
- [UEEX margin prices](https://www.ueex.com.ua/exchange-quotations/natural-gas/margin-price/):
  the stated gas day and exact sale, weighted short-term, and purchase rows are
  checked. Only the explicit no-VAT values are accepted.

Public access is not proof of permission to redistribute an archive. Licensing,
automated collection frequency and publication remain review items. Raw responses
are local ignored artifacts, and tests use synthetic examples, not copied history.

## Contract

- CEGHIX: only `CEGH VTP DA YYYY-MM-DD` contracts with an explicit CEGHIX price.
  Trading date and delivery date remain distinct; EUR/MWh, VAT unspecified.
  Missing CEGHIX is never replaced with VWAP, CEGHEDI or zero. Weekend/holiday
  contracts are counted as unsupported rather than expanded into invented daily data.
- UEEX: monthly VTT resource weighted prices in UAH/1000m3, separately for all
  payment terms, prepayment and postpayment. Delivery date means the first day of
  the resource month, not a daily delivery. Quote date means the displayed fixing
  date, not the webpage snapshot date. Hidden EUR spans are never read as UAH.
- UEEX fixing dates before 2022-07-01 are explicitly counted as unsupported VAT
  rows. Supported values retain the source's VAT-excluded basis. There is no tax,
  currency or energy/volume conversion. Empty UEEX cells and explicit `-` markers
  are counted as missing; malformed nonempty tokens fail the batch.
- UEEX margin observations are three separate daily series: marginal sale,
  weighted short-term standardized products, and marginal purchase. They retain
  UAH/1000m3 excluding VAT and the page's gas day. The VAT-inclusive companion
  rows are checked for structural completeness but are not imported.
- Decimal values must be finite and positive. Unknown headers, duplicate accepted
  keys, malformed dates, wrong provenance or ambiguous price cells fail visibly.
  Nested spans/tables, merged cells and unclosed table structure are rejected to
  prevent partial-price extraction. Malformed DA labels fail rather than being
  counted as unsupported contracts; delivery dates are checked even for missing prices.
- Source freshness must be within seven calendar days: latest accepted trading
  date for CEGHIX, explicit page snapshot date for UEEX. This is a conservative
  prototype threshold, not a trading-calendar implementation. Sparse history is
  not advertised as complete daily coverage.
- Every observation carries the raw SHA256, official URL and timezone-aware
  `available_at` equal to retrieval time. No historical publication timestamp is
  invented. This snapshot is unsuitable for point-in-time historical backtests.

## Run

From the repository in PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m market_forecast.gas_indices_dry_run --output-dir data/gas-index-prototype/my-new-run
```

Use a new output directory each time. The command makes only three fixed-endpoint
HTTP GET requests (redirects disabled, 10 MB response cap, bounded timeouts).
It writes raw responses before parsing, a manifest with hashes/counts/errors,
and `observations.json` only after both source batches validate. A failing run
returns a nonzero exit code and retains diagnostic evidence. Local artifact I/O
errors also propagate; this is not a transactional storage implementation.

For a network-free replay add `--replay-dir <previous-run-directory>`. Replay
verifies stored SHA256 hashes and preserves the original retrieval timestamp;
freshness is evaluated at that timestamp, not falsely refreshed to today.
The output manifest explicitly labels replay mode.

There is intentionally no `--write`, database URL, `.env` loading or persistence
adapter import. Do not wire this into production without a separate review.

## Live verification

The first live dry-run preserved both raw responses and failed closed on a real
empty UEEX payment cell. That source case now has a synthetic regression test.
Reparsing those exact saved bytes with the corrected parser validated:

| Source | Accepted prices | Missing prices | Explicitly excluded |
|---|---:|---:|---|
| CEGHIX DA | 16 | 9 | 20 non-DA contract rows |
| UEEX monthly VTT | 137 | 7 | 31 legacy VAT rows |

These are snapshot observations, not a complete historical import. After the
successful local replay, a fresh live dry-run completed on 2026-09-09 at 06:35 UTC
with the same accepted/excluded counts and status `validated`. Local evidence is
in `data/gas-index-prototype/run-20260909-03/`: raw responses, manifest and 153
normalized observations. These ignored artifacts are not synchronized via Git.
No database was opened or changed by the prototype.

A new live dry-run on 2026-09-21 validated all three current source responses:

| Source | Accepted prices | Missing prices | Explicitly excluded |
|---|---:|---:|---|
| CEGHIX DA | 15 | 9 | 21 non-DA contract rows |
| UEEX monthly VTT | 139 | 8 | 31 legacy VAT rows |
| UEEX margin prices | 3 | 0 | 0 |

For gas day 2026-09-20 the accepted no-VAT margin observations were sale
16,076.63, weighted short-term 17,862.92, and purchase 19,649.21 UAH/1000m3.
The ignored local evidence is in `data/gas-index-prototype/run-20260921-01/`.

Before extending scope: confirm redistribution terms; model weekend/holiday gas
delivery and older VAT regimes explicitly; specify required coverage and revision
history; then review any proposed persistence integration separately.
