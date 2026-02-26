# Paperless Task Status UI Specification

## Goal

Show Paperless ingestion status in the ScanExpress UI without blocking further scan interactions.

After each upload submission, ScanExpress must:

- track the Paperless task identified by the UUID returned from `/api/documents/post_document/`,
- show task progress in the UI,
- keep the latest 10 task entries visible at the bottom of the page in descending (newest-first) order,
- keep updating each entry until its status is no longer `STARTED`,
- add a link to the created Paperless document once available.

## Scope

In scope:

- Backend parsing of Paperless upload response that may be a raw UUID string.
- Backend endpoint for polling task state from Paperless by `task_id`.
- Frontend task history list rendering and polling behavior.
- Non-blocking UI behavior while task polling continues.

Out of scope:

- Multi-user realtime synchronization across browser sessions.
- Replacing existing scan/stream progress UX.

## Current Behavior (Baseline)

- `POST /api/scan` performs scan, TIFF->PDF conversion, and upload to Paperless.
- Upload response is currently parsed as JSON object only; raw UUID string responses are ignored.
- UI only shows a single status line and timing metrics.
- No task polling against `/api/tasks/?task_id=<uuid>`.

## Functional Requirements

### 1) Upload response parsing

When Paperless upload returns a JSON string UUID (example: `"cf13eea8-5c7a-40b8-aac8-bd8bdc315769"`), backend must treat it as `paperless_task_id`.

If upload returns a JSON object, backend should preserve existing behavior and additionally extract task id when present.

Expected result from `POST /api/scan` success payload:

- `status: "ok"`
- `paperless_task_id: <uuid|null>`
- keep existing fields (`message`, `timing_metrics`, device fields, etc.).

### 2) Backend task status proxy endpoint

Add a backend endpoint so frontend never needs direct Paperless token access.

Proposed endpoint:

- `GET /api/paperless/tasks/<task_id>`

Behavior:

- Uses current user token and configured Paperless base URL.
- Calls Paperless endpoint `/api/tasks/?task_id=<task_id>`.
- Returns normalized JSON payload for the UI.
- Handles Paperless/network failures with structured error JSON.

Normalized response (success):

- `status: "ok"`
- `task_id: <uuid>`
- `task_status: <STARTED|SUCCESS|FAILURE|...>`
- `related_document: <string|null>`
- `result: <string|null>`
- `date_done: <string|null>`
- `task_file_name: <string|null>`
- `raw_task: <object|null>` (optional passthrough for debugging)

If Paperless returns no matching task array item, backend returns:

- HTTP 404
- `status: "error"`
- `message: "Task not found"`

### 3) Frontend task history list (last 10)

Add a task status section at the bottom of `templates/index.html`.

Recent upload history source of truth:

- Backend in-memory history, segmented per current user.
- Frontend loads history from `GET /api/recent-uploads` on page load.

Required presentation:

- Title: `Recent uploads`.
- List of max 10 entries.
- Newest entry at top.
- Each entry shows:
  - local timestamp (submission time),
  - filename (if known),
  - current Paperless status,
  - concise result/error text when available,
  - document link when `related_document` is available.

Link behavior on success:

- Build document URL as:
  - `<paperless_base_url>/documents/<related_document>`
- Open in new tab.

### 4) Polling lifecycle

For each scan result that includes `paperless_task_id`:

- Add/replace entry in local in-memory list.
- Start background polling for that task immediately.
- Poll interval: 2 seconds (configurable constant in `static/app.js`).
- Continue polling while `task_status === "STARTED"`.
- Stop polling when status is not `STARTED`.
- Backend updates server-side recent-upload entries as task poll responses are normalized.

Terminal states:

- `SUCCESS`: mark entry complete, render document link if `related_document` present.
- `FAILURE`: mark entry failed, show `result` message.
- any other non-`STARTED` status: treat as terminal, show raw status text.

### 5) Non-blocking UI behavior

Task polling must never block scan interaction.

Required behavior:

- Existing scan button/device controls stay governed by scan lock behavior only.
- Background polling uses asynchronous fetch and timer scheduling.
- A long-running or failed task poll must not freeze rendering or disable controls.
- Multiple task polls may run concurrently (up to the number of active entries in last 10).

### 6) List retention and ordering

List management rules:

- Keep at most 10 entries.
- Insert newest at top.
- Drop oldest when count exceeds 10.
- If same `task_id` is received again, update existing entry in place and keep ordering by original submission timestamp unless explicitly refreshed by a new submission event.

## Error Handling Requirements

Backend:

- Never log token values.
- Include actionable messages for network timeout, HTTP 4xx/5xx, parse errors.
- Return JSON errors consistently (`status`, `message`).

Frontend:

- Poll errors update the affected entry (`poll_error`) but do not remove it.
- Use retry backoff after repeated poll failures (minimum: cap retries at fixed interval; recommended: exponential up to 15s).
- Polling failures must not overwrite scan status banner for active scan flow.

## API Contract Additions

`POST /api/scan` success addendum:

- `paperless_task_id` (string UUID or `null`)

New endpoint:

- `GET /api/paperless/tasks/<task_id>`
- `GET /api/recent-uploads`

Example normalized success body:

    {
      "status": "ok",
      "task_id": "11e48898-bde8-4695-afd6-5a61452a4b54",
      "task_status": "SUCCESS",
      "related_document": "21",
      "result": "Success. New document id 21 created",
      "date_done": "2026-02-24T14:33:09.254628+01:00",
      "task_file_name": "Offer.pdf"
    }

Example normalized failure body:

    {
      "status": "ok",
      "task_id": "cf13eea8-5c7a-40b8-aac8-bd8bdc315769",
      "task_status": "FAILURE",
      "related_document": "1",
      "result": "...It is a duplicate...",
      "date_done": "2026-02-24T13:27:03.844895+01:00",
      "task_file_name": "262227845924-3-1.pdf"
    }

## UI State Model (Frontend)

Per task entry fields:

- `taskId`
- `submittedAt`
- `fileName`
- `taskStatus`
- `resultText`
- `relatedDocumentId`
- `documentUrl`
- `isPolling`
- `lastError`
- `lastUpdatedAt`

Collection:

- `recentPaperlessTasks: TaskEntry[]` (max length 10)

## Acceptance Criteria

1. After a scan upload, when Paperless returns UUID, UI creates a new recent entry within one render cycle.
2. Entry status transitions from `STARTED` to terminal state automatically without manual refresh.
3. Successful entry shows clickable Paperless document link using `related_document`.
4. Failed entry shows error/result text and no success link.
5. Latest 10 entries only, descending order by newest submission.
6. User can trigger another scan while previous entries continue polling (subject to existing device scan lock semantics).
7. No Paperless tokens are exposed in frontend code or browser network calls to Paperless directly.

## Test Plan (Implementation Guidance)

Backend unit tests (`tests/test_app_batch.py`):

- Parse upload response when body is JSON UUID string.
- Parse upload response when body is object.
- Normalize task response for `STARTED`, `SUCCESS`, `FAILURE`.
- Error response when Paperless task list is empty.

Frontend/e2e (`tests/e2e/smoke.spec.js`):

- Simulate upload returning UUID and task status sequence `STARTED -> SUCCESS`.
- Verify recent list renders newest-first and max 10 behavior.
- Verify success link appears with `/documents/<id>` target.
- Verify polling does not prevent initiating another scan flow once scan lock permits.

## Implementation Notes

- Keep existing routes and architecture; add only minimal endpoint/UI section required.
- Maintain compatibility with existing synchronous `/api/scan` payload consumers.
- Prefer small helper functions for parsing upload responses and normalizing task payloads.
- Keep backend/frontend status wording consistent.
