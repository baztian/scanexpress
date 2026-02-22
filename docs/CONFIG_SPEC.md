# Configuration Specification

## Overview

ScanExpress uses Python's built-in `configparser` module to manage multi-user scanner configurations and device presets.

**Goals:**

- Single source of truth: `config.ini` file with user and device definitions
- Multi-user support: each user has own token and device presets
- Device templates: users can define and quickly switch between preset scanner configurations
- Simple enough to edit manually; extensible to database-backed storage later
- Environment variable fallback for backwards compatibility during transition

---

## Configuration File Location

- **Default:** `config.ini` in the app root directory
- **Can be overridden:** `SCANEXPRESS_CONFIG_FILE` environment variable
- **Initial setup:** Copy `config.sample.ini` to `config.ini` and customize for your environment

---

## Configuration Structure

### User Configuration

Each user gets its own section: `[user:<username>]`

    [user:alice]
    paperless_api_token = abc123def456ghi789

**Keys:**

- `paperless_api_token` (required): Token for uploading to Paperless-ngx

---

## Device Templates

Users can define device presets under: `[user:<username>:device:<device_name>]`

    [user:alice:device:brother-color]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_timeout_seconds = 30
    resolution = 300
    mode = 24 bit Color

    [user:alice:device:brother-bw]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_timeout_seconds = 30
    resolution = 200
    mode = Gray

    [user:bob:device:canon-default]
    device_id = Canon:usb:123:456
    scan_command = /usr/bin/scanimage
    scan_timeout_seconds = 40
    resolution = 150
    mode = 24 bit Color

**Keys:**

- `device_id` (required): Device identifier passed to scanner command via `-d` flag
- `scan_command` (optional): Device-specific scan command. If not provided, uses `SCANEXPRESS_SCAN_COMMAND` env var
- `scan_timeout_seconds` (optional): Timeout per page during scanning for this device (integer seconds)
- Additional keys are arbitrary and passed as device-specific settings (reserved for future UI/API expansion)

---

## Complete Example Config

    [global]
    paperless_base_url = https://paperless.example.com
    scan_timeout_seconds = 30
    paperless_timeout_seconds = 5

    [user:alice]
    paperless_api_token = token_alice_secret_123
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh

    [user:alice]
    paperless_api_token = token_alice_secret_123

    [user:alice:device:brother-color]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_timeout_seconds = 30
    resolution = 300
    mode = 24 bit Color
    brightness = 100

    [user:alice:device:brother-bw]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_timeout_seconds = 30
    resolution = 200
    mode = Gray

    [user:bob]
    paperless_api_token = token_bob_secret_456

    [user:bob:device:canon-default]
    device_id = Canon:usb:123:456
    scan_command = /usr/bin/scanimage
    scan_timeout_seconds = 40
    resolution = 150
    mode = 24 bit Color

---

## Environment Variables

These settings remain in environment variables (not config file):

- `SCANEXPRESS_PAPERLESS_BASE_URL` (required): Base URL of Paperless-ngx instance (no trailing slash)
- `SCANEXPRESS_PAPERLESS_API_TOKEN_FALLBACK` (optional): Fallback API token if user token not set in config
- `SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS` (default: 5): Timeout per page during upload to Paperless-ngx
- `SCANEXPRESS_SCAN_COMMAND` (default: `scanimage`): Default scan command if not specified in device config
- `SCANEXPRESS_CURRENT_USER` (required in Phase 1): Username to use for scanning

---

## Implementation Approach

### Config Module (`config.py`)

A new module will handle all config access:

    from configparser import ConfigParser
    from pathlib import Path

    class ConfigManager:
        """Manages reading and accessing ScanExpress configuration."""

        def __init__(self, config_file: Path | None = None):
            """Initialize config manager and load configuration."""
            # Load config.ini from path, env var, or default location

        def get_user_token(self, username: str) -> str:
            """Get Paperless API token for user."""

        def get_user_device(self, username: str, device_name: str) -> dict:
            """Get device template settings as dict."""

        def list_user_devices(self, username: str) -> list[str]:
            """List available device templates for a user."""

        def user_exists(self, username: str) -> bool:
            """Check if user is configured."""

**Behavior:**

- Load config once on app startup
- Reload config on-demand (for future web UI edits)
- Validate required sections and keys exist

---

## Device Selection

When a scan is triggered, the caller can specify which device template to use:

**Phase 1 (current):**

- Use first available device for the user (or specified via env var `SCANEXPRESS_DEVICE_NAME`)

**Phase 2 (future):**

- Frontend provides device selection UI (dropdown of user's templates)
- API call: `POST /api/scan?user=alice&device=brother-color`

---

## Sample Configuration File

A `config.sample.ini` file is provided in the repository as a starting point.

Setup steps:

1. Copy `config.sample.ini` to `config.ini`
2. Edit `config.ini`:

   - Update user sections with actual Paperless API tokens
   - Add/modify device templates with your scanner settings
   - Set device_id values specific to your hardware
   - Adjust scan_timeout_seconds for each device if needed

3. Set `SCANEXPRESS_CURRENT_USER` in `/etc/default/scanexpress`
4. Start the app

---

## Validation & Error Handling

On app startup:

1. Load config.ini from configured location
2. Validate required keys exist:

   - `[user:SCANEXPRESS_CURRENT_USER]` section must exist
   - User section must have `paperless_api_token` key

3. Validate env vars are set:

   - `SCANEXPRESS_PAPERLESS_BASE_URL` must be configured
   - `SCANEXPRESS_CURRENT_USER` must be set

4. On missing/invalid config, return clear error message

Example error:

    ERROR: SCANEXPRESS_CURRENT_USER=alice but user 'alice' not found in config.ini.
    Available users: bob, charlie

---

## File Permissions

- `config.ini` should be readable by the service user
- Restrict read permissions: `640` or `600` (contains secrets)
- Ownership: `root:scanexpress` or similar

    sudo chown root:scanexpress /etc/scanexpress/config.ini
    sudo chmod 640 /etc/scanexpress/config.ini

---

## Testing

### Manual Testing

1. Copy `config.sample.ini` to test config:

       cp config.sample.ini test_config.ini

2. Edit `test_config.ini` with test user and device
3. Start app with test config:

       export SCANEXPRESS_CONFIG_FILE=test_config.ini
       export SCANEXPRESS_CURRENT_USER=testuser
       python app.py

4. Verify config is loaded: check logs or add debug endpoint

### Unit Tests

- `test_config.py`: Test ConfigManager parsing, validation
- `test_app.py`: Update existing tests to mock config instead of only env vars

---

## Deployment

### Initial Setup

1. Clone repo and install dependencies
2. Copy `config.sample.ini` to `config.ini`
3. Edit `config.ini` with actual users, tokens, and devices
4. Set environment variables in service file or `/etc/default/scanexpress`
5. Set file permissions on `config.ini`
6. Start app

### Example Service File

    [Service]
    Environment="SCANEXPRESS_CURRENT_USER=alice"
    Environment="SCANEXPRESS_PAPERLESS_BASE_URL=https://paperless.example.com"
    EnvironmentFile=/etc/default/scanexpress
    ExecStart=/opt/scanexpress/.venv/bin/python /opt/scanexpress/app.py

### Example `/etc/default/scanexpress`

    # Configuration file location (optional)
    # SCANEXPRESS_CONFIG_FILE=/etc/scanexpress/config.ini

    # Required: Paperless-ngx base URL
    SCANEXPRESS_PAPERLESS_BASE_URL=https://paperless.example.com

    # Required in Phase 1: user to use for scanning
    SCANEXPRESS_CURRENT_USER=alice

    # Optional: default scan command (used if device doesn't specify one)
    # SCANEXPRESS_SCAN_COMMAND=/opt/scanexpress/scripts/scan_wrapper.sh

    # Optional: timeout per page during Paperless upload (default: 5 seconds)
    # SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS=5

---

## Future Migration to SQLite

This design is extensible to a database backend:

1. Create `config_db.py` with same interface as `config.py`
2. Update `app.py` to detect and use DB config if present
3. Add admin UI to edit config (writes to DB, not INI)
4. DB can be seeded from INI on first run

**No breaking changes:** config.ini remains valid, used for deployment / initial values.

---

**Old:**

    def _build_scan_command(batch_output_pattern: Path) -> list[str]:
        configured_command = os.getenv("SCANEXPRESS_SCAN_COMMAND")
        scanner_device = os.getenv("SCANEXPRESS_SCANNER_DEVICE", "").strip()

**New:**

    def _build_scan_command(batch_output_pattern: Path, username: str) -> list[str]:
        # Get from config; fall back to env vars for backwards compat
        config_manager = get_config_manager()
        configured_command = config_manager.get_user_scan_command(username) or os.getenv(...)
        scanner_device = config_manager.get_device_id(username) or os.getenv(...)

---

## User Identification

**Phase 1 (current):**

- Single hardcoded user via environment variable
- `SCANEXPRESS_CURRENT

- Single hardcoded user via environment variable
- `SCANEXPRESS_CURRENT_USER` env var (e.g., `alice`)
- Or default to first user in config if env var not set

Example `.venv/bin/activate` or `/etc/default/scanexpress`:

    export SCANEXPRESS_CURRENT_USER=alice

**Phase 2 (future):**

- `POST /api/scan?user=alice`
- Or `POST /api/scan` with header `X-Scan-User: alice`

---

## Environment Variable Fallback (Migration Path)

During transition, the config manager will **prefer config.ini but fall back to env vars**:
    def get_global(self, key: str, fallback_env: str | None = None) -> str:
        # 1. Try config.ini [global] section
        # 2. If not found, try fallback env var
        # 3. Return default or raise error

**Fallback mappings:**

**Fallback mappings:**

- `global.paperless_base_url` → `SCANEXPRESS_PAPERLESS_BASE_URL`
- `global.scan_timeout_seconds` → `SCANEXPRESS_SCAN_TIMEOUT_SECONDS`
- `global.paperless_timeout_seconds` → `SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS`
- `user:<username>.paperless_api_token` → `SCANEXPRESS_PAPERLESS_API_TOKEN`
- `user:<username>.scan_command` → `SCANEXPRESS_SCAN_COMMAND`
- `user:<username>:device:<device>.device_id` → `SCANEXPRESS_SCANNER_DEVICE`

This allows a gradual migration: old deployments keep working, new ones use `config.ini`.

---

## API Contract (Frontend)

Currently, the frontend calls `POST /api/scan` or `POST /api/scan/stream` without any user context.

- Scan endpoint uses configured `SCANEXPRESS_CURRENT_USER`
- Response includes `username` field (for logging/debugging)

## Documentation Updates

- [README.md](../README.md): Update installation section with config.ini setup
- [DEVELOPMENT.md](./DEVELOPMENT.md): Add config file examples for local testing
- [AGENTS.md](../AGENTS.md): Update constraints if needed
