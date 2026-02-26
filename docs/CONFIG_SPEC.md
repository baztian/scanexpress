# Configuration Specification

## Overview

ScanExpress uses Python's built-in `configparser` module to manage multi-user scanner configurations and device presets.

**Goals:**

- Single source of truth: `config.ini` file with user and device definitions
- Multi-user support: each user has own token and device presets
- Device templates: users can define and quickly switch between preset scanner configurations
- Simple enough to edit manually; extensible to database-backed storage later
- Environment variable override support for custom config file location

---

## Configuration File Location

- **Default lookup order:**
    1. `~/.config/scanexpress/scanexpress.conf`
    2. `/etc/scanexpress.conf`
- **Can be overridden:** `SCANEXPRESS_CONFIG_FILE` environment variable
- **Initial setup:** Copy `scanexpress.sample.conf` to `/etc/scanexpress.conf` and customize for your environment

---

## Configuration Structure

### Global Configuration

Global settings are defined in section `[global]`.

Filename template setting:

- `filename_template` (optional): Template used to generate the default filename basename shown in the UI.
- Default fallback when unset: `scan_{scan_uuid}`.
- Placeholder requirement: template should contain `{scan_uuid}` or `{base62_id}` to preserve uniqueness.
- Canonical placeholder: `{scan_uuid}`.
- Backward compatibility: `{base62_id}` is still supported.
- If configured value is invalid (missing supported placeholders), runtime falls back to `scan_{scan_uuid}`.

Session secret setting:

- `secret_key` (recommended): Flask session signing secret.
- Resolution precedence: `SCANEXPRESS_SECRET_KEY` environment variable first, then `[global].secret_key`.
- If neither is set, runtime falls back to a development default secret.

Examples:

- `filename_template = scan_{scan_uuid}`
- `filename_template = inbox_{scan_uuid}`
- `filename_template = scan_{base62_id}`

### User Configuration

Each user gets its own section: `[user:<username>]`

    [user:alice]
    paperless_api_token = abc123def456ghi789

**Keys:**

- `paperless_api_token` (required): Token for uploading to Paperless-ngx
- `default_device` (required when one or more device templates exist): Explicit default device template name for this user
- `default_scanimage_params_device` (optional): Device template name whose scanimage params should be used by default

---

## Device Templates

Users can define device presets under: `[user:<username>:device:<device_name>]`

    [user:alice:device:brother-color]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_output_mode = batch
    scan_timeout_seconds = 30

    [user:alice:device:brother-color:scanimage-params]
    resolution = 300
    mode = 24 bit Color

    [user:alice:device:brother-bw]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_output_mode = batch
    scan_timeout_seconds = 30

    [user:alice:device:brother-bw:scanimage-params]
    resolution = 200
    mode = Gray

    [userbrother-:bob:device:canon-default]
    device_id = Canon:usb:123:brother --456
    scan_command = /usr/bin/scanimage
    scan_output_mode = single_file
    scan_timeout_seconds = 40

    [user:bob:device:canon-default:scbrother-animage-params]
    resolution = 150
    mode = 24 bit Color

**Keys:**

- `device_id` (optional): Device identifier passed to scanner command via `-d` flag. If unset, scanner command runs without `-d`.
- `scan_command` (optional): Device-specific scan command. If not provided, backend defaults to `scanimage`.
- `scan_output_mode` (required): Scanner output strategy. Allowed values:
    - `batch`: use `--batch=<pattern>`
    - `single_file`: use `--output-file=<path>`
- `scan_timeout_seconds` (optional): Timeout per page during scanning for this device (integer seconds)

Note: `scanimage` does not natively accept `...:libusb:/dev/<symlink>` device identifiers. This `/dev/...` form is a ScanExpress convenience syntax.

### Device ID Format & Stability

The `device_id` is passed to `scanimage` with the `-d` flag. USB device addresses (e.g. `:001:002`) can change when a scanner is unplugged and replugged, breaking your configuration. To create a stable reference, use a udev rule to create a persistent symlink.

**Without udev (not recommended):**

Using numeric USB addresses is simple but fragile:

    device_id = BrotherADS2200:libusb:001:002

When you unplug and replug the scanner, the device numbers change and your config becomes invalid.

**With udev (recommended):**

Create a udev rule to generate a persistent symlink to your scanner:

1. Find your scanner's USB vendor and product IDs:

       lsusb

   Example output:

       Bus 001 Device 003: ID 04f9:03fb Brother Industries, Ltd. ADS-2200

   The IDs are `04f9` (vendor) and `03fb` (product).

2. Create a udev rule file at `/etc/udev/rules.d/99-brother-scanner.rules`:

       cat << 'EOF' | sudo tee /etc/udev/rules.d/99-brother-scanner.rules >/dev/null
       SUBSYSTEM=="usb", ATTRS{idVendor}=="04f9", ATTRS{idProduct}=="03fb", SYMLINK+="brother-scanner"
       EOF

3. Reload and trigger udev rules:

       sudo udevadm control --reload-rules
       sudo udevadm trigger

4. Verify the symlink was created:

       ls -la /dev/brother-scanner

5. Update your device configuration to use the symlink:

       device_id = BrotherADS2200:libusb:/dev/brother-scanner

    This is intentionally not a standard `scanimage` device specifier. At runtime, ScanExpress resolves `/dev/brother-scanner` to `/dev/bus/usb/BBB/DDD` and invokes `scanimage -d BrotherADS2200:libusb:BBB:DDD`.

Now your device reference is stable across unplug/replug cycles.

### Scanimage Parameters (Dynamic)

Preferred location for scanner CLI options:

`[user:<username>:device:<device_name>:scanimage-params]`

All keys in this section are passed through dynamically as scan command args:

- key `resolution = 300` -> `--resolution 300`
- key `mode = Gray` -> `--mode Gray`
- key `source = Automatic Document Feeder` -> `--source "Automatic Document Feeder"`
- underscores are converted to dashes (example: `contrast_adjustment = 10` -> `--contrast-adjustment 10`)

Fallback behavior:

- If `:scanimage-params` section is missing, additional non-reserved keys from `[user:<username>:device:<device_name>]` are treated as scan command args.
- Reserved keys in device section are not passed through as scanimage args: `device_id`, `scan_command`, `scan_output_mode`, `scan_timeout_seconds`.

---

## Complete Example Config

    [global]
    secret_key = replace-with-long-random-secret
    paperless_base_url = https://paperless.example.com
    scan_timeout_seconds = 30
    paperless_timeout_seconds = 5
    filename_template = scan_{scan_uuid}

    [user:alice]
    paperless_api_token = token_alice_secret_123
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh

    [user:alice]
    paperless_api_token = token_alice_secret_123

    [user:alice:device:brother-color]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_output_mode = batch
    scan_timeout_seconds = 30

    [user:alice:device:brother-color:scanimage-params]
    resolution = 300
    mode = 24 bit Color
    brightness = 100

    [user:alice:device:brother-bw]
    device_id = BrotherADS2200:libusb:001:002
    scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
    scan_output_mode = batch
    scan_timeout_seconds = 30

    [user:alice:device:brother-bw:scanimage-params]
    resolution = 200
    mode = Gray

    [user:bob]
    paperless_api_token = token_bob_secret_456

    [user:bob:device:canon-default]
    device_id = Canon:usb:123:456
    scan_command = /usr/bin/scanimage
    scan_output_mode = single_file
    scan_timeout_seconds = 40

    [user:bob:device:canon-default:scanimage-params]
    resolution = 150
    mode = 24 bit Color

---

## Environment Variables

Runtime settings are config-only.

Only optional environment variable:

- `SCANEXPRESS_CONFIG_FILE`: path override for `config.ini`.
- `SCANEXPRESS_SECRET_KEY`: overrides `[global].secret_key` for Flask session signing.

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

- If device templates exist for a user, `[user:<username>] default_device` must be set and that template is used.
- If no device templates exist, scanning runs without a `-d` device parameter.

Scanimage parameter profile selection:

- If `[user:<username>] default_scanimage_params_device` is set, that template supplies default scanimage params.
- Otherwise, the selected active device template supplies scanimage params.

**Phase 2 (future):**

- Frontend provides device selection UI (dropdown of user's templates)
- API call: `POST /api/scan?user=alice&device=brother-color`

---

## Sample Configuration File

A `scanexpress.sample.conf` file is provided in the repository as a starting point.

Setup steps:

1. Copy `scanexpress.sample.conf` to `/etc/scanexpress.conf`
2. Edit `/etc/scanexpress.conf`:

    - Set `[global] default_user` (or leave empty to require login)
    - Set `[global] paperless_base_url`
   - Update user sections with actual Paperless API tokens
   - Set per-user `password_hash` values when login-required mode is used
   - Add/modify device templates with your scanner settings
   - Set device_id values specific to your hardware
   - Adjust scan_timeout_seconds for each device if needed

3. Start the app

---

## Validation & Error Handling

On app startup:

1. Load config file from configured location (default lookup order: `~/.config/scanexpress/scanexpress.conf`, then `/etc/scanexpress.conf`)
2. Validate required keys exist:

    - `[global] default_user` is optional (auto-login mode)
    - If `[global] default_user` is set, `[user:<global.default_user>]` section must exist
    - If `[global] default_user` is empty, each login-enabled `[user:<username>]` should contain `password_hash`
   - User section must have `paperless_api_token` key

    3. Validate optional filename template format when configured:

        - If `[global] filename_template` is set, it should include `{scan_uuid}` or `{base62_id}`.
        - If missing or invalid, app falls back safely to `scan_{scan_uuid}`.

    4. On missing/invalid config, return clear error message

Example error:

    ERROR: global.default_user=alice but user 'alice' not found in scanexpress.conf.
    Available users: bob, charlie

---

## File Permissions

- Config file should be readable by the service user
- Restrict read permissions: `640` or `600` (contains secrets)
- Ownership: `root:scanexpress` or similar

    sudo chown root:scanexpress /etc/scanexpress.conf
    sudo chmod 640 /etc/scanexpress.conf

---

## Testing

### Manual Testing

1. Copy `scanexpress.sample.conf` to test config:

    cp scanexpress.sample.conf test_config.ini

2. Edit `test_config.ini` with test user and device
3. Start app with test config:

       export SCANEXPRESS_CONFIG_FILE=test_config.ini
       python app.py

4. Verify config is loaded: check logs or add debug endpoint

### Unit Tests

- `test_config.py`: Test ConfigManager parsing, validation
- `test_app.py`: Update existing tests to mock config instead of only env vars

---

## Deployment

### Initial Setup

1. Clone repo and install dependencies
2. Copy `scanexpress.sample.conf` to `/etc/scanexpress.conf`
3. Edit `/etc/scanexpress.conf` with actual users, tokens, and devices
4. Set file permissions on `/etc/scanexpress.conf`
5. Start app

### Example Service File

    [Service]
    # Optional only when config path is non-default:
    # Environment="SCANEXPRESS_CONFIG_FILE=/etc/scanexpress.conf"
    ExecStart=/opt/scanexpress/.venv/bin/python /opt/scanexpress/app.py

---

## Future Migration to SQLite

This design is extensible to a database backend:

1. Create `config_db.py` with same interface as `config.py`
2. Update `app.py` to detect and use DB config if present
3. Add admin UI to edit config (writes to DB, not INI)
4. DB can be seeded from INI on first run

**Authentication migration note:** this is a breaking change for auth keys; the old global active-user key has been replaced by `global.default_user`.

---

**Runtime behavior:**

    def _build_scan_command(batch_output_pattern: Path, username: str) -> list[str]:
        config_manager = get_config_manager()
        configured_command = config_manager.get_user_scan_command(username)
        scanner_device = config_manager.get_device_id(username)

---

## User Identification

**Phase 1 (current):**

- Optional auto-login via `[global] default_user`; otherwise authenticated session user.

**Phase 2 (future):**

- `POST /api/scan?user=alice`
- Or `POST /api/scan` with header `X-Scan-User: alice`

---

## API Contract (Frontend)

Currently, the frontend calls `POST /api/scan` or `POST /api/scan/stream` without any user context.

- Scan endpoint uses resolved authenticated user or `[global] default_user`
- Response includes `username` field (for logging/debugging)

## Documentation Updates

- [README.md](../README.md): Update installation section with config.ini setup
- [DEVELOPMENT.md](./DEVELOPMENT.md): Add config file examples for local testing
- [AGENTS.md](../AGENTS.md): Update constraints if needed
