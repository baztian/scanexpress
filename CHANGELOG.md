# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Added

- No changes yet.

## [0.0.3] - 2026-03-14

### Changed

- Added more detailed logging around PDF conversion, Paperless upload attempts, and scan failures.

### Fixed

- Reduced scan memory and disk usage by converting TIFF pages to PDF incrementally instead of loading all pages at once.
- Temporary TIFF files are deleted after conversion, and empty scanner output pages are ignored when valid pages are present.
- Improved Canon scanner compatibility by allowing conversion of truncated TIFF images.

## [0.0.2] - 2026-02-27

### Added

- Docker support for running ScanExpress in containerized environments.
- Initial work to publish ScanExpress images to Docker Hub.

### Documentation

- README now mentions Docker image availability on Docker Hub.

## [0.0.1] - 2026-02-26

### Added

- Flask app entrypoint and web UI scaffold for ScanExpress.
- `POST /api/scan` and `POST /api/scan/stream` scan workflows with scanner invocation, PDF conversion, and Paperless upload integration.
- Scanner device template model with per-user and shared device definitions.
- Config-first runtime settings via `scanexpress.conf` with optional `SCANEXPRESS_CONFIG_FILE` override.
- User login/logout flow with session secret support and configuration validation UI.
- Recent uploads list and Paperless task status polling support.
- Playwright e2e smoke coverage and Python unit test suite for config and API behavior.

### Documentation

- Deployment, architecture, configuration, development, release, and feature-spec docs under `docs/`.
- Service unit template and sample configuration for server installs.

[0.0.1]: https://github.com/baztian/scanexpress/releases/tag/v0.0.1
[0.0.2]: https://github.com/baztian/scanexpress/compare/v0.0.1...v0.0.2
[0.0.3]: https://github.com/baztian/scanexpress/compare/v0.0.2...v0.0.3
[Unreleased]: https://github.com/baztian/scanexpress/compare/v0.0.3...HEAD
