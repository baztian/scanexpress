# ScanExpress UI Finalization Spec

## Purpose

This spec defines the production UI baseline for ScanExpress. The app is no longer treated as a scaffold. UI behavior and styling must be implemented as a stable, user-facing experience.

## Scope

In scope:

- Align visual language (colors + typography) with Paperless-ngx documentation styling from <https://docs.paperless-ngx.com>.
- Use a Paperless-like top banner treatment (green background with white title/subtitle text).
- Replace device/config dropdown selection with a radio-button model.
- Group configurations under each device ID while preserving single selection.
- Replace the current raw recent upload list with a structured, readable recent scans list/table.
- Add a background flash effect when a scan completes and the scan button becomes available again.

Out of scope:

- New pages, modals, filters, or dashboard widgets.
- Backend API shape changes unless required for accessibility text or display-only metadata.

## Visual Theme Requirements

Reference source:

- <https://docs.paperless-ngx.com>

Extracted Paperless docs tokens to mirror:

- Primary brand green: `#17541f` (`--paperless-green`).
- Primary accent green: `#2b8a38` (`--paperless-green-accent`).
- Link green: `#21652a`.
- Default text color: near-black (`#000000de` equivalent on light background).
- Default background: white.
- Font family: `Roboto`, with system sans-serif fallback.
- Monospace font (only where needed): `Roboto Mono`, then system monospace fallback.

The implementation must:

- Introduce CSS variables in the app UI for the above tokens.
- Apply `Roboto` globally to body text, labels, buttons, table text, and status lines.
- Use brand green for primary interactive emphasis (scan button active state, key headings, focus outlines as appropriate).
- Keep contrast at WCAG AA minimum for text and controls.

## Information Architecture

Single-page structure remains:

1. Header/title + concise subtitle.
2. Device/config selection section.
3. Selected configuration details.
4. Primary scan action + status.
5. Recent scans history.

## Device and Configuration Selection

### Replace Select With Radio Inputs

Current control:

- Remove/select deprecate `select#deviceSelect` UX from page flow.

New control:

- Use a radio group (`fieldset` + `legend`) for all selectable scan configurations.
- Exactly one configuration can be selected at a time (native radio exclusivity via same `name`).
- If a default device/config exists from backend payload, preselect it.
- If no option is available, disable scan button and show explicit status message.

### Grouping Rule

Group options by `device_id` and show each device as a visual group with nested config choices.

Expected grouping model:

- Group header: the shared `device_id`.
- Child radio options: each config template that resolves to that `device_id`.
- Option label should include user-meaningful name (template name) and short key params summary.

Example conceptual hierarchy:

- Device `brother_ads_2200`
  - `default` (300dpi, color)
  - `duplex_bw` (300dpi, gray, duplex)
- Device `fujitsu_ix500`
  - `receipt_mode` (200dpi, gray)

Selection semantics:

- Selecting any child config sets the active `selectedDeviceName` used by existing scan API requests.
- Backend-facing value remains config template name unless backend contract changes explicitly.

## Recent Scans Presentation

Current state is a plain concatenated text list. Replace with a structured view.

Required presentation:

- Use either:
  - semantic table (`table`) for desktop-first readability, or
  - a clearly columnized list if responsive constraints require.

Preferred fields (columns):

- Submitted time.
- Device/config label.
- File name.
- Task ID (shortened display allowed, full value preserved in title/tooltip).
- Task status.
- Result/error summary.
- Document link action (when available).

Behavior requirements:

- Newest entries first.
- Maximum 10 entries retained (existing cap).
- Polling transitions must update row/list item in place (no duplicates for same task ID).
- Status text should use visual badges/chips or clear labels for `STARTED`, `PENDING`, `SUCCESS`, `FAILURE`.
- `Open document` must remain keyboard accessible and open in new tab safely.

## Scan Completion Background Flash

Add a subtle feedback flash when scan processing cycle completes and the scan button returns to enabled state.

Trigger condition:

- Fire exactly when scan action transitions from unavailable/busy to available again for the selected device.
- Covers both success and terminal error completion.

Visual behavior:

- Flash the full page background (`body`) once using a light tint derived from Paperless accent green.
- Duration target: 2 seconds total, single pulse only.
- Must not loop or strobe.
- Respect reduced-motion preference:
  - if `prefers-reduced-motion: reduce`, use immediate non-animated state change cue or very short fade.

Implementation note:

- Event should be state-driven (button enabled transition), not tied only to HTTP success callback, so UI stays correct with polling and error paths.

## Accessibility Requirements

- Device selection uses semantic `fieldset`/`legend` and labeled radios.
- Focus order remains logical from top to bottom.
- Keyboard-only interaction supports selecting radios and starting scan.
- Status updates use text that can be read by assistive tech (existing status node can remain, but must stay synchronized).
- Table/list markup must keep headers/labels programmatically associated.

## Performance and Robustness

- Keep vanilla JS architecture (`static/app.js`) without additional frameworks.
- Avoid full re-render of unrelated sections on each poll tick when possible.
- No regressions to existing polling/backoff logic.

## Acceptance Criteria

1. Theme and typography:

- UI uses Roboto and Paperless-like green palette from this spec.
- Primary button and key accents visually match Paperless docs tone.

1. Device selection:

- Dropdown is removed from active UI.
- Radios are grouped by `device_id`.
- Only one config can be selected globally.
- Scan button is disabled when no selectable config is active.

1. Recent scans:

- Recent scans render as readable table/list with structured columns/fields.
- Entries update in place by task ID and show terminal outcomes clearly.
- Document link appears for successful tasks with related document.

1. Completion flash:

- Background flash occurs once each time scan cycle completes and button re-enables.
- Works for both success and failure terminal outcomes.
- Reduced-motion preference is respected.

1. Regression safety:

- Existing `/api/scan` and Paperless task polling workflow remains functional.
- Existing e2e scenario for recent upload polling still passes after UI adaptation.

## Implementation Targets

Primary files expected for this spec implementation:

- `templates/index.html`
- `static/app.js`

Optional (if style extraction from HTML is preferred):

- `static/app.css`

## Notes for Implementation PR

- Keep markup and script IDs stable where practical to avoid unnecessary test churn.
- If changing selectors in e2e tests, update `tests/e2e/smoke.spec.js` in the same change.
- Include before/after screenshots in PR for desktop width and narrow/mobile width.
