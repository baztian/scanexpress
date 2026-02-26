# ScanExpress Development & Deployment Guide

This guide describes a simple iterative workflow when developing on a desktop PC and validating on a production server with real scanner hardware and real Paperless-ngx.

For one-time server installation and service bootstrap, see the "Server Installation" section in `README.md`.

## Local Development Quick Start

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open `http://localhost:8000`.

To test the full `/api/scan` flow locally (TIFF→PDF conversion), also install Pillow:

    pip install "Pillow>=10.3,<13.0"

Developer note: production default config path is `/etc/scanexpress.conf`. For local non-root development, use `SCANEXPRESS_CONFIG_FILE` to point to a writable test file (for example `tests/e2e/test_config.ini`).

## Python Unit Tests

Run unit tests with the repository virtual environment so Flask and other Python dependencies resolve correctly.

Preferred (works even without activating the venv):

    .venv/bin/python -m unittest tests/test_config.py tests/test_app_batch.py

Alternative (after activation):

    source .venv/bin/activate
    python -m unittest tests/test_config.py tests/test_app_batch.py

## Playwright Smoke Tests

Install Node dependencies and Playwright browser binaries:

    npm install
    npx playwright install

Run the smoke suite (auto-starts Flask via `python app.py`):

    npm run test:e2e

Optional modes:

    npm run test:e2e:headed
    npm run test:e2e:ui

### E2E strategy for scanner + Paperless

- E2E smoke tests start the real Flask app and call the real `/api/scan` backend endpoint.
- Hardware is not used in tests: Playwright config points `SCANEXPRESS_CONFIG_FILE` to `tests/e2e/test_config.ini`, which uses `scripts/fake_scan_wrapper.py` as device `scan_command`.
- Paperless network dependency is not used in tests: `tests/e2e/smoke.spec.js` starts a local fake Paperless HTTP server on `127.0.0.1:18089`.
- Scanner behavior is controlled per test by writing `success`, `adf`, or `fail` to `/tmp/scanexpress-fake-scan-mode.txt`.

## Recommended Iteration Stages

1. Desktop checks (fast): run local app + e2e smoke tests.
2. Production server hardware check: real scanner, fake Paperless endpoint.
3. Production server full integration: real scanner + real Paperless-ngx.

This keeps failures easy to isolate:

- Stage 2 failing means scanner side issue.
- Stage 3 failing (after stage 2 passes) usually means Paperless/network/auth issue.

## Option A: Git-Based Update Loop (Recommended)

Best when you already commit frequently.

### Iteration cycle

On desktop:

    git add .
    git commit -m "scanexpress: tweak"
    git push

On production server:

    cd /opt/scanexpress
    git pull --ff-only
    source .venv/bin/activate
    pip install -r requirements.txt
    sudo systemctl restart scanexpress
    sudo journalctl -u scanexpress -n 80 --no-pager

## Option B: rsync-Based Update Loop

Best for rapid experimental changes before committing.

On desktop (run from repo root):

    rsync -az --delete \
      --exclude '.git' \
      --exclude '.venv' \
      --exclude '__pycache__' \
      --exclude 'test-results' \
      ./ deploy@<server-host>:/opt/scanexpress/

On production server:

    cd /opt/scanexpress
    source .venv/bin/activate
    pip install -r requirements.txt
    sudo systemctl restart scanexpress
    sudo journalctl -u scanexpress -n 80 --no-pager

If you mix rsync and later run `git pull` in the same tree, clean first:

    git reset --hard HEAD
    git clean -fd
    git pull --ff-only

## systemd Service Notes

Template file: `scanexpress.service.template`.

Install/bootstrap steps are documented in `README.md`.

### If code path differs

Edit unit values (`WorkingDirectory`, `ExecStart`, optional `Environment`) in:

    sudo systemctl edit --full scanexpress

Then reload and restart:

    sudo systemctl daemon-reload
    sudo systemctl restart scanexpress

## Quick Validation Commands on Production Server

    curl -sS -X POST http://127.0.0.1:8000/api/scan | jq .
    sudo journalctl -u scanexpress -f

If `/api/scan` returns `status=error`, the message is designed to identify scanner vs conversion vs Paperless upload failures.
