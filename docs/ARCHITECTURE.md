# ScanExpress Architecture (Draft)

## Intended Flow

1. User opens the Flask-served web page and clicks the scan button.
2. Frontend JavaScript sends a request to the Flask API endpoint.
3. Flask backend executes configured scanner command/wrapper (`scanimage` compatible) and captures TIFF output.
4. Backend converts TIFF pages to a PDF.
5. Backend uploads PDF to Paperless-ngx (`/api/documents/post_document/`).
6. Flask API returns success/failure status for the UI.

## Notes

- Scanner model should be configurable (not hardcoded).
- Credentials and endpoints should come from environment variables.
- API and frontend are kept in one project for simplicity.
- Playwright smoke tests (`tests/e2e/smoke.spec.js`) validate the UI/API contract against the local Flask server.
- E2E avoids real hardware by using a fake scan wrapper command and a local fake Paperless endpoint.
