# AGENTS.md

Guidance for AI coding agents working in `scanexpress`.

## Project Snapshot

- App type: Flask web app with server-rendered entry page and small frontend JS.
- Backend entrypoint: `app.py`.
- Frontend files: `templates/index.html`, `static/app.js`.
- Current state: scaffold only; `/api/scan` returns `501 not_implemented`.
- Intended direction: trigger local scanner hardware and send results to Paperless-ngx.

## Architecture Constraints

- Keep the app simple: one Flask service, one HTML template, one frontend JS file unless a change requires refactoring.
- Preserve current route structure unless asked:
  - `GET /` renders the UI
  - `POST /api/scan` triggers scanning flow
- Prefer incremental changes over broad rewrites.
- Keep backend and frontend behavior in sync (status values/messages).

## Coding Standards

- Python:
  - Follow existing Flask style in `app.py`.
  - Keep functions small and explicit.
  - Use environment variables for endpoints, credentials, device paths, and external integrations.
  - Do not hardcode secrets or host-specific paths.
- JavaScript:
  - Keep to vanilla JS (no framework additions unless explicitly requested).
  - Handle network and parse errors gracefully.
  - Keep UI state text clear and concise.
- HTML:
  - Avoid unnecessary complexity; keep controls accessible and semantic.

## Integration Expectations (When Implementing Scan)

- Scanner invocation should be isolated behind a backend function/module to support testing.
- Add timeouts and actionable error messages for scanner failures.
- Validate file outputs before upload steps.
- Paperless-ngx integration should:
  - read base URL + auth from environment variables,
  - fail safely with useful error responses,
  - avoid logging sensitive headers/tokens.

## Testing & Verification

- Minimum checks after code changes:
  1. App starts: `python app.py`
  2. `/` loads and button click updates status text
  3. `/api/scan` behavior matches expected status code/payload
- For UI or `/api/scan` contract changes, also run `npm run test:e2e`.
- If tests are added, keep them focused and lightweight (do not introduce heavy frameworks without request).

## Documentation Rules

- Update `README.md` for any new setup steps, env vars, or behavior changes.
- Keep `docs/ARCHITECTURE.md` aligned when changing flow or major components.
- For command/script examples in Markdown docs, use 4-space-indented blocks; do not use triple-backtick fenced code blocks.
- Always include blank lines before and after lists for readability.
- Add blank lines before and after all headings (e.g., `## Heading` with blank line above and below).
- Never use multiple consecutive blank lines; maximum one blank line between sections.
- No trailing spaces at end of lines.

## Safe Defaults

- Prefer explicit config over implicit assumptions.
- Return structured JSON errors from API endpoints.
- Avoid destructive operations and shell commands that can alter system scanner state unless requested.

## Suggested Environment Variables

When integration work starts, standardize on names like:

- `SCANEXPRESS_SCANNER_DEVICE`
- `SCANEXPRESS_SCAN_OUTPUT_DIR`
- `SCANEXPRESS_PAPERLESS_BASE_URL`
- `SCANEXPRESS_PAPERLESS_API_TOKEN`
- `SCANEXPRESS_SCAN_TIMEOUT_SECONDS`
- `SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS`

(Only document/add what is actually implemented.)
