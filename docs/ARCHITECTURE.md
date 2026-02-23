# ScanExpress Architecture (Draft)

## Intended Flow

1. User opens the Flask-served web page and clicks the scan button.
2. Frontend JavaScript sends a request to the Flask progress-stream endpoint.
3. Flask backend resolves current user and active device via `ConfigManager` (`config.ini` first, env fallback).
4. Flask backend executes configured scanner command/wrapper (`scanimage` compatible) with batch output (`--batch=.../scan_output%d.tiff`).
5. Backend converts all generated TIFF output files/pages to a PDF.
6. Backend uploads PDF to Paperless-ngx (`/api/documents/post_document/`).
7. Flask API returns success/failure status for the UI.

### API Notes

- `POST /api/scan`: synchronous JSON response (compatible with scripts and curl).
- `POST /api/scan/stream`: streaming NDJSON progress updates for live UI status during scanning.
- Successful responses include `username` (and `device_name` when resolved) for traceability.

## Notes

- Scanner model should be configurable (not hardcoded).
- Credentials and scanner settings should come from `config.ini` (`ConfigManager`), with environment variable fallback for backward compatibility.
- API and frontend are kept in one project for simplicity.
- Playwright smoke tests (`tests/e2e/smoke.spec.js`) validate the UI/API contract against the local Flask server.
- E2E avoids real hardware by using a fake scan wrapper command and a local fake Paperless endpoint.
