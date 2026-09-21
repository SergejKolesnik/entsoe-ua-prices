# Repository instructions

## Purpose

This repository collects, validates, stores, analyzes, and later forecasts Ukrainian day-ahead electricity market data.
It is independent from Solar Monitoring System. Changes here must never affect its production workflow.

## Working mode

Optimize for correctness, safety, and token efficiency.

Before making changes:

1. Identify the smallest set of files relevant to the task.
2. Inspect those files first.
3. Search the repository only when the location of relevant code is unknown.
4. Do not scan or summarize the entire repository unless explicitly requested.
5. Do not read all of `PROJECT_CONTEXT.md` by default; search for the relevant heading or keyword and read only the needed context.
6. Reuse information already obtained in the current task instead of reopening unchanged files.

Prefer small, targeted changes over broad refactoring.

## Token efficiency

Keep tool use and responses concise.

- Prefer targeted file search over directory-wide inspection.
- Avoid repeatedly reading unchanged files or printing large file contents.
- Do not restate architecture documented here or produce long reasoning summaries unless requested.
- When logs are large, inspect the relevant error section first.
- Investigate a failing test before running broader diagnostics.
- Run targeted tests during development; run the full required suite only when the change is ready for validation.
- Avoid speculative exploration of unrelated modules; stop once evidence supports a safe fix.

For routine work, use the least expensive reasoning path that can complete the task reliably. Escalate analysis only when the issue remains unresolved or has architectural or security implications.

## Safety

- Never commit `.env`, API tokens, database credentials, raw production exports, or service-account files.
- Never expose secrets in logs, screenshots, test output, comments, or responses.
- Invalid, incomplete, stale, or unexpected source data must fail visibly.
- Never replace missing prices or measurements with zero.
- Preserve raw source responses before normalization when ingestion persistence is implemented.
- Do not rewrite Git history or force-push without explicit user approval.
- Direct pushes to `main` require explicit user confirmation. Use a feature branch and pull request by default.

## Repository context

`PROJECT_CONTEXT.md` is the canonical detailed project history and decision log. Use it as a reference, not mandatory full-session context.

For gas, forecasting, VDR, neighboring markets, flows, weather, Neon, Streamlit, Hermes, or ingestion, search for the relevant heading or keyword and inspect only that section first.

Read the complete file only when the task changes project-wide architecture, a cross-domain dependency is unclear, or the user explicitly requests a full project review.

## Architecture

- `sources/` fetches raw source responses and does not persist or interpret market values.
- `parsers/` converts raw source formats into domain records.
- `validation/` checks completeness and invariants without repairing data.
- `persistence/` owns database access.
- Presentation code must not silently mutate source data.
- Forecasting logic must remain leakage-safe.
- Gas-market functionality remains a bounded context separate from DAM contracts.
- VDR data remains separate from DAM data.
- SQLite is the local fallback; Neon is used only through configured database access.
- Runtime secrets must never be committed.

## Change strategy

For each task:

1. Locate the relevant code.
2. Confirm the current behavior.
3. Make the smallest coherent change.
4. Add or update the narrowest relevant tests.
5. Run those tests.
6. If they pass, run the broader validation required for completion.
7. Report only material results.

Do not refactor unrelated code while fixing a localized issue. Mention a beneficial broader refactor separately instead of including it automatically.

## Neon and database changes

Treat production Neon writes as sensitive operations.

Before changing persistence or schemas:

- Inspect the relevant migration and repository code.
- Determine whether the operation is read-only or mutating.
- Prefer a development or staging branch/database when available.
- Use dry-run or read-only validation where supported.
- Preserve idempotency and verify retries cannot duplicate or overwrite valid historical data.

Production database changes and destructive SQL require explicit user approval unless the task already contains that approval.

## Google Sheets

Google Sheets used as source data are read-only by default.

- Never modify source worksheets unless the user explicitly authorizes it.
- Do not infer missing values or silently normalize ambiguous source structures.
- Preserve source-specific contracts.
- Import commands should default to dry-run when supported.

## Git workflow

Before changing code, work from the canonical repository state, confirm the active branch, and use a feature branch by default.

After changes, do not push directly to `main` without explicit approval. Prefer a pull request and report any uncommitted, unpushed, or unmerged work. Do not create unrelated commits.

## Commands

Use targeted tests first. For example:

```bash
python -m unittest tests.test_relevant_module -v
```

Before declaring repository-level completion, when applicable run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

Forecast CLI:

```bash
python -m market_forecast.cli --help
```

Set `PYTHONPATH=src` when running directly from a checkout that has not been installed. Do not repeatedly rerun the full suite when a targeted test can answer the current question.

## Failure handling

When a command fails:

1. Inspect the actual error.
2. Identify the likely relevant file or dependency.
3. Make one targeted correction.
4. Rerun the narrowest useful check.

Do not immediately perform a repository-wide audit after a localized failure. If the same approach fails twice, reassess the hypothesis before continuing.

## Definition of done

- Behavior changes have appropriate tests.
- Relevant targeted tests pass.
- The full unit-test suite and compile check pass when required by the scope.
- README and `PROJECT_CONTEXT.md` are updated only when architecture, configuration, data contracts, or project state materially change.
- No secrets or production data were added.
- Database and source-data safety rules were preserved.
- Uncommitted, unpushed, or unmerged work is reported explicitly.

## Final response format

For normal implementation tasks, keep the final response short:

1. Changed — files and behavior.
2. Verified — tests and checks run.
3. Remaining — only unresolved items, risks, or required approval.

Do not repeat the task description or provide a long project summary unless requested.
