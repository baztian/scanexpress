# ScanExpress

ScanExpress is a planned web app for triggering scanner jobs (for example a Brother ADS-2200 connected through a Raspberry Pi) from a browser, then sending scanned output to a Paperless-ngx server.

## Design

- Backend + web serving: Python (Flask)
- Frontend: JavaScript + HTML (served by Flask)
- Target integration: Scanner hardware via host device (Raspberry Pi or equivalent)
- Output destination: Paperless-ngx

## Quick Start

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py
    # open http://localhost:8000

## Backend Scan + Upload Configuration

`POST /api/scan` now performs this pipeline:

1. Execute scanner command (expects TIFF on stdout)
2. Convert TIFF pages to a single PDF
3. Upload PDF to Paperless-ngx `/api/documents/post_document/`

Configure with environment variables:

- `SCANEXPRESS_SCAN_COMMAND` (optional): scanner command (binary path or command prefix) to run instead of `scanimage`. Backend appends `-d <device>` (when configured) and `--format=tiff` so wrappers should keep a scanimage-compatible interface and forward args.
- `SCANEXPRESS_SCANNER_DEVICE` (optional): scanner device name used by default scan command (or by wrapper script).
- `SCANEXPRESS_SCAN_TIMEOUT_SECONDS` (optional, default `60`): timeout for scanner command.
- `SCANEXPRESS_PAPERLESS_BASE_URL` (required for upload): e.g. `https://paperless.example.com`.
- `SCANEXPRESS_PAPERLESS_API_TOKEN` (required for upload): Paperless token used as `Authorization: Token ...`.
- `SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS` (optional, default `60`): timeout for Paperless upload request.

Example wrapper configuration:

    export SCANEXPRESS_SCAN_COMMAND="./scripts/scan_wrapper.sh"
    export SCANEXPRESS_SCANNER_DEVICE="BrotherADS2200:libusb:001:014"
    export SCANEXPRESS_PAPERLESS_BASE_URL="https://paperless.cloud.zonny.de:43443"
    export SCANEXPRESS_PAPERLESS_API_TOKEN="<mysecrettoken>"
    python app.py

## Playwright Smoke Tests

Install Node dependencies and Playwright browser binaries:

    npm install
    npx playwright install

Run the smoke suite (auto-starts Flask via `python app.py`):

    npm run test:e2e

### E2E strategy for scanner + Paperless

- E2E smoke tests start the real Flask app and call the real `/api/scan` backend endpoint.
- Hardware is not used in tests: Playwright config sets `SCANEXPRESS_SCAN_COMMAND` to `scripts/fake_scan_wrapper.py`.
- Paperless network dependency is not used in tests: `tests/e2e/smoke.spec.js` starts a local fake Paperless HTTP server on `127.0.0.1:18089`.
- Scanner behavior is controlled per test by writing `success` or `fail` to `/tmp/scanexpress-fake-scan-mode.txt`.

Optional modes:

    npm run test:e2e:headed
    npm run test:e2e:ui

## License

MIT (see [LICENSE](LICENSE)).
