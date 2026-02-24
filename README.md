# ScanExpress

ScanExpress is a planned web app for triggering scanner jobs (for example a Brother ADS-2200 connected through a Raspberry Pi) from a browser, then sending scanned output to a Paperless-ngx server.

## Design

- Backend + web serving: Python (Flask)
- Frontend: JavaScript + HTML (served by Flask)
- Target integration: Scanner hardware via host device (Raspberry Pi or equivalent)
- Output destination: Paperless-ngx

## Development and Testing

For local development setup, Playwright e2e smoke tests, and iterative deployment workflows, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Server Installation

Use this section for one-time server setup. Use the development guide for iterative update workflows.

Prerequisites:

- Server has scanner drivers/tools installed and can run `scanimage`.
- Python 3 with venv support is available.
- `python3-pil` package is installed on the server.

Install required system packages:

    sudo apt update
    sudo apt install -y python3-venv python3-pil

One-time app install:

    sudo mkdir -p /opt/scanexpress
    sudo chown "$USER":"$USER" /opt/scanexpress
    git clone https://github.com/baztian/scanexpress /opt/scanexpress
    cd /opt/scanexpress
    python3 -m venv --system-site-packages .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Note: with `--system-site-packages`, `pip` may warn about unrelated global package conflicts.

Optional (isolated venv, no global packages):

    pip install -r requirements.txt "Pillow>=10.3,<13.0"

Create service account and group:

    sudo groupadd --system scanexpress
    sudo useradd --system --gid scanexpress --create-home --home /var/lib/scanexpress --shell /usr/sbin/nologin scanexpress

Create config file from sample:

    sudo cp /opt/scanexpress/scanexpress.sample.conf /etc/scanexpress.conf
    sudo chown root:scanexpress /etc/scanexpress.conf
    sudo chmod 640 /etc/scanexpress.conf

Edit `/etc/scanexpress.conf` and set `global.current_user`, `global.paperless_base_url`, real user tokens, and scanner device templates.

Optional: if your config file is stored at a non-default path, set `SCANEXPRESS_CONFIG_FILE` in your service unit environment.

Install service from `scanexpress.service.template`:

    sudo cp /opt/scanexpress/scanexpress.service.template /etc/systemd/system/scanexpress.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now scanexpress
    sudo systemctl status scanexpress --no-pager

Quick validation:

    curl -sS -X POST http://127.0.0.1:8000/api/scan
    sudo journalctl -u scanexpress -n 80 --no-pager

## Backend Scan + Upload Configuration

`POST /api/scan` now performs this pipeline:

1. Execute scanner command using batch TIFF output (`--batch=/tmp/.../scan_output%d.tiff`)
2. Convert all generated TIFF pages/files to a single PDF
3. Upload PDF to Paperless-ngx `/api/documents/post_document/`

For live UI progress updates, the frontend uses `POST /api/scan/stream` (NDJSON stream) and updates status as scan pages complete.

On successful completion, scan responses include `timing_metrics` (`total_seconds`, `scan_seconds`, `paperless_seconds`, `scan_seconds_per_page`, `paperless_seconds_per_page`) and the UI status message includes these values.

Configuration resolution is **config-first with env fallback**:

- `config.ini` user + device sections are primary source for token, scan command, device id, and per-device scan timeout.
- `config.ini` `:scanimage-params` subsection is the preferred source for scanner command options; keys are passed through dynamically as CLI args.
- `config.ini` `[global]` is primary source for `paperless_base_url`, `scan_timeout_seconds`, and `paperless_timeout_seconds`.
- `config.ini` `[global]` also defines `current_user`.
- `config.ini` `[user:<username>]` supports:
  - `default_device` (required when user has one or more `[user:<username>:device:*]` templates) to choose the default scanner template deterministically.
  - `default_scanimage_params_device` (optional) to choose which device template supplies default `scanimage` parameters.

See full schema and examples in [docs/CONFIG_SPEC.md](docs/CONFIG_SPEC.md).

Environment variables:

- `SCANEXPRESS_CONFIG_FILE` (optional): path to config file.

Default config lookup order when `SCANEXPRESS_CONFIG_FILE` is not set:

- `~/.config/scanexpress/scanexpress.conf`
- `/etc/scanexpress.conf`

Dynamic scanner args from config:

- Preferred: define arbitrary scanner options in `[user:<username>:device:<device_name>:scanimage-params]`.
- Each key/value is passed to scanner as `--<key> <value>` (underscores become dashes).
- Compatibility fallback: when `:scanimage-params` is absent, extra non-reserved keys in `[user:<username>:device:<device_name>]` are also passed as scanner args.
- If no `device_id` is configured for the selected/default template, ScanExpress runs the scan command without the `-d` argument.

## License

MIT (see [LICENSE](LICENSE)).
