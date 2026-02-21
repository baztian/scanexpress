# ScanExpress Architecture (Draft)

## Intended Flow

1. User opens the Flask-served web page and clicks the scan button.
2. Frontend JavaScript sends a request to the Flask API endpoint.
3. Flask backend triggers scanner command on host hardware.
4. Backend receives output file(s).
5. Backend uploads file(s) to Paperless-ngx.
6. Flask API returns success/failure status for the UI.

## Notes

- Scanner model should be configurable (not hardcoded).
- Credentials and endpoints should come from environment variables.
- API and frontend are kept in one project for simplicity.
- Playwright smoke tests (`tests/e2e/smoke.spec.js`) validate the UI/API contract against the local Flask server.
