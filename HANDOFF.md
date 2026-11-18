# RDN Market Intelligence — Handoff

- Last updated: 2026-09-21
- Main SHA: 15d9c48

## Current state

Main contains the RDN/DAM collection, validation, persistence, contextual market data, and Streamlit dashboard workflow. Source Google Sheets remain read-only; production jobs use configured secrets and must not be changed without approval.

## Last completed branch

- branch: codex/optimize-agent-instructions
- PR: #50
- status: MERGED
- changed: streamlined repository agent instructions for targeted, safe work.
- verified: documentation-only change; no application test run recorded here.

## Active work

- branch: codex/project-handoff-workflow
- PR: #51
- status: READY
- changed: adds the project handoff file, branch-completion protocol, and PR template.
- tests/checks: GitHub PR Tests / test (pull_request) passed in 33 seconds; compare shows 3 changed files.
- database/migration changes: none.
- production impact: none.
- unresolved issues: none.

## Open items

- Review and merge PR #51.
- Keep Google Sheets imports read-only unless explicitly approved.
- Treat production Neon writes and migrations as explicit-approval operations.
- Keep DAM, gas, and VDR contracts isolated.
- Preserve missing values and source-native units, VAT basis, and delivery dates.
- Run only targeted validation unless code or repository-wide contracts change.

## Important current constraints

- Google Sheets are read-only.
- Production Neon writes require explicit approval.
- No direct push to main.
- Use a feature branch and pull request.
- Never commit secrets.
- Do not touch unrelated local files.

## Recommended next action

Review and merge PR #51; then confirm main and delete the feature branch if it is no longer needed.

## New chat startup

A new chat must read:

1. AGENTS.md
2. HANDOFF.md
3. Only the relevant section of PROJECT_CONTEXT.md
4. Only the relevant code files

Do not perform a repository-wide scan by default.
