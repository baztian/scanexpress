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

## Playwright Smoke Tests

Install Node dependencies and Playwright browser binaries:

    npm install
    npx playwright install

Run the smoke suite (auto-starts Flask via `python app.py`):

    npm run test:e2e

Optional modes:

    npm run test:e2e:headed
    npm run test:e2e:ui

## License

MIT (see [LICENSE](LICENSE)).
