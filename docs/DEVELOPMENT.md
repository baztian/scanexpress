# ScanExpress Development & Deployment Guide

This guide describes a simple iterative workflow when developing on a desktop PC and validating on a production server with real scanner hardware and real Paperless-ngx.

For one-time server installation and service bootstrap, see the "Server Installation" section in `README.md`.

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

## systemd Service Notes

Template file: `scanexpress.service.template`.

Install/bootstrap steps are documented in `README.md`.

### If code path differs

Edit unit values (`WorkingDirectory`, `ExecStart`, `EnvironmentFile`) in:

    sudo systemctl edit --full scanexpress

Then reload and restart:

    sudo systemctl daemon-reload
    sudo systemctl restart scanexpress

## Quick Validation Commands on Production Server

    curl -sS -X POST http://127.0.0.1:8000/api/scan | jq .
    sudo journalctl -u scanexpress -f

If `/api/scan` returns `status=error`, the message is designed to identify scanner vs conversion vs Paperless upload failures.
