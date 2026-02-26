# Filename Input Specification

## Purpose

Define the product and technical behavior for allowing users to provide a scan filename from a UI input field while preserving a safe default naming strategy.

The feature must support:

- user-editable filename base,
- deterministic default naming using a Base62 identifier,
- automatic `.pdf` suffix handling behind the scenes.

## Scope

In scope:

- Single filename input field in the existing scan UI.
- Default value template and generated default value.
- Input focus/click behavior to support overwrite-on-type.
- Backend filename normalization and `.pdf` suffix enforcement.
- API contract additions needed to pass and return filename metadata.

Out of scope:

- Multi-file naming batches.
- User-defined extension selection.
- Persisting custom filename defaults across sessions.

## Naming Model

### Default Template

The default value template is configurable via `config.ini`.

Config behavior:

- If configured and valid, use the configured template value.
- If not configured, fallback template is `scan_{scan_uuid}`.
- If configured but invalid (missing supported placeholders), fallback template is `scan_{scan_uuid}`.

Fallback template:

- `scan_{scan_uuid}`

Equivalent f-string representation:

- `f"scan_{scan_uuid}"`

Recommended config key:

- `filename_template` (in `config.ini`)

Template requirement:

- Must include `{scan_uuid}` or `{base62_id}` placeholder so generated names remain unique by default.
- `{scan_uuid}` is the canonical placeholder.
- `{base62_id}` remains supported for backward compatibility.

### Base62 Identifier Composition

`scan_uuid` is composed of:

- `base62_timestamp`: Base62-encoded timestamp component.
- `base62_random`: 2-character Base62-encoded random component.

Concatenation rule:

- `{scan_uuid} = {base62_timestamp}{base62_random}`

Example generated basename:

- `scan_5D749c95rE`

Where:

- `5D749c95` is the Base62 timestamp component.
- `rE` is the 2-character Base62 random component.

User-visible example full filename after backend normalization:

- `scan_5D749c95rE.pdf`

## UX Requirements

### Filename Input Field

- A single text input labeled `Filename` is shown in the scan controls area.
- The field displays basename only (without `.pdf`).
- Initial value is generated from the default template (`scan_{scan_uuid}`).

### Overwrite-First Interaction

When the user first clicks or tabs into the filename field for a scan action:

- all characters in the current value are selected,
- the next typed character replaces the full selected value.

Behavior details:

- Select-all occurs on focus and click for convenience.
- If user intentionally places caret after selection, normal editing is allowed.
- Re-select-on-every-keystroke must not happen.

### Validation Feedback

- Empty basename is not allowed at submission time.
- Leading/trailing whitespace is trimmed before validation.
- If invalid after trimming, scan action is blocked with clear inline status text.

## Backend Normalization Rules

At submit time, backend treats client input as basename and enforces a single `.pdf` suffix.

Normalization algorithm:

1. Read provided basename.
2. Trim surrounding whitespace.
3. Remove any trailing `.pdf` (case-insensitive) from basename input.
4. If resulting basename is empty, return validation error.
5. Construct final filename as `{basename}.pdf`.

Examples:

- `scan_5D749c95rE` -> `scan_5D749c95rE.pdf`
- `invoice_2026.pdf` -> `invoice_2026.pdf`
- `  receipt_01  ` -> `receipt_01.pdf`

## API Contract Changes

### Request

`POST /api/scan` accepts optional field:

- `filename_base` (string, basename without extension expected)

If omitted, backend generates default basename from `scan_{scan_uuid}`.

Default generation source:

- configured valid `filename_template` from `config.ini`, or
- fallback `scan_{scan_uuid}` when not configured or invalid.

### Response

Successful response includes:

- `filename_base` (normalized basename used)
- `filename` (final file name with `.pdf` suffix)

Error response for validation failure includes:

- `status: "error"`
- `message` with actionable text (example: `Filename cannot be empty`).

## Accessibility Requirements

- Input has visible label and programmatic label association.
- Select-all interaction works with both mouse and keyboard focus.
- Validation errors are announced through existing status text region.

## Acceptance Criteria

1. On page load, filename input shows a value matching `scan_{scan_uuid}` pattern.

2. Clicking into the field selects the entire value so typing overwrites it.

3. Submitted filename always ends with exactly one `.pdf` in backend processing.

4. If user enters value already ending in `.pdf`, backend does not duplicate extension.

5. Empty or whitespace-only values are rejected with clear error messaging.

6. If no value is provided, backend generates default basename and continues scan.

7. If `filename_template` is configured in `config.ini` with `{scan_uuid}` or `{base62_id}`, generated default basename follows that template.

8. If `filename_template` is configured without a supported placeholder, backend falls back to `scan_{scan_uuid}`.

## Test Plan (Implementation Guidance)

Backend tests:

- Default basename generation follows `scan_{scan_uuid}` shape.
- 2-character random Base62 component is present.
- Normalization appends one `.pdf` and de-duplicates provided extension.
- Empty/whitespace basename returns validation error.

Frontend/e2e tests:

- Input initializes with generated default basename.
- Focus/click selects all text in input.
- Typing after focus replaces full default value.
- Submitted custom basename appears as `.pdf` in result metadata.

## Implementation Targets

Primary files expected for implementation:

- `templates/index.html`
- `static/app.js`
- `app.py`
- `tests/test_app_batch.py`
- `tests/e2e/smoke.spec.js`
