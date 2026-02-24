import json
import re
import select
import shlex
import subprocess
import tempfile
import threading
import time
from queue import Queue
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from config import ConfigManager

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    Image = None
    UnidentifiedImageError = OSError

app = Flask(__name__)
_CONFIG_MANAGER: ConfigManager | None = None
_TIMEOUT_COUNTDOWN_START_SECONDS = 15
_DEVICE_SCAN_LOCK = threading.Lock()
_ACTIVE_DEVICE_SCANS: dict[str, dict[str, object]] = {}
_PAPERLESS_UPLOAD_MAX_ATTEMPTS = 3
_PAPERLESS_UPLOAD_RETRY_BASE_DELAY_SECONDS = 0.5
_PAPERLESS_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ScanInProgressError(RuntimeError):
    pass


def get_config_manager() -> ConfigManager:
    global _CONFIG_MANAGER
    if _CONFIG_MANAGER is None:
        _CONFIG_MANAGER = ConfigManager()
    return _CONFIG_MANAGER


def _resolve_libusb_device_id(scanner_device: str) -> str:
    match = re.match(r"^(?P<prefix>(?:.*:)?libusb:)(?P<device_path>/dev/.+)$", scanner_device)
    if match is None:
        return scanner_device

    device_path = match.group("device_path")
    try:
        resolved_path = Path(device_path).resolve(strict=True)
    except OSError:
        return scanner_device

    usb_path_match = re.search(
        r"/dev/bus/usb/(?P<bus>\d{3})/(?P<devnum>\d{3})$", resolved_path.as_posix()
    )
    if usb_path_match is None:
        return scanner_device

    return (
        f"{match.group('prefix')}"
        f"{usb_path_match.group('bus')}:{usb_path_match.group('devnum')}"
    )


def _build_scan_command(
    batch_output_pattern: Path, username: str | None = None, device_name: str | None = None
) -> list[str]:
    configured_command = None
    scanner_device = None
    scanimage_params: dict[str, str] = {}
    if username is not None:
        config_manager = get_config_manager()
        configured_command = config_manager.get_user_scan_command(username, device_name)
        scanner_device = config_manager.get_device_id(username, device_name)
        scanimage_params = config_manager.get_device_scanimage_params(username, device_name)

    if configured_command and configured_command.strip() != "":
        command = shlex.split(configured_command)
    else:
        command = ["scanimage"]

    if scanner_device:
        resolved_device_id = _resolve_libusb_device_id(scanner_device)
        command.extend(["-d", resolved_device_id])

    scan_output_mode = "batch"
    if username is not None:
        scan_output_mode = config_manager.get_device_scan_output_mode(username, device_name)

    for key in sorted(scanimage_params):
        option_name = key.strip().replace("_", "-")
        if not option_name:
            continue

        option_value = scanimage_params[key].strip()
        command.append(f"--{option_name}")
        command.append(option_value)

    command.append("--format=tiff")
    if scan_output_mode == "single_file":
        single_output_path = _build_single_output_tiff_path(batch_output_pattern)
        command.append(f"--output-file={single_output_path}")
    else:
        command.append(f"--batch={batch_output_pattern}")
    return command


def _resolve_scan_output_mode(username: str | None, device_name: str | None) -> str:
    if username is None:
        return "batch"
    return get_config_manager().get_device_scan_output_mode(username, device_name)


def _build_single_output_tiff_path(batch_output_pattern: Path) -> Path:
    batch_stem = batch_output_pattern.stem.replace("%d", "")
    return batch_output_pattern.parent / f"{batch_stem}.tiff"


def _resolve_scan_device_details(
    username: str | None, device_name: str | None
) -> tuple[str | None, str | None]:
    if username is None:
        return None, None

    config_manager = get_config_manager()
    configured_device_id = config_manager.get_device_id(username, device_name)
    if configured_device_id is None:
        return None, None

    scanimage_device_name = _resolve_libusb_device_id(configured_device_id)
    return configured_device_id, scanimage_device_name


def _resolve_scan_lock_device_id(
    username: str,
    device_name: str | None,
    configured_device_id: str | None = None,
    scanimage_device_name: str | None = None,
) -> str:
    if scanimage_device_name is None and configured_device_id is None:
        configured_device_id, scanimage_device_name = _resolve_scan_device_details(
            username, device_name
        )

    if scanimage_device_name is not None:
        return scanimage_device_name

    if configured_device_id is not None:
        return configured_device_id

    fallback_device_name = device_name if device_name is not None else "__default__"
    return f"{username}:{fallback_device_name}"


def _acquire_device_scan_lock(device_lock_id: str, username: str, device_name: str | None) -> None:
    with _DEVICE_SCAN_LOCK:
        if device_lock_id in _ACTIVE_DEVICE_SCANS:
            raise ScanInProgressError(
                f"Scan already in progress for device_id '{device_lock_id}'."
            )

        _ACTIVE_DEVICE_SCANS[device_lock_id] = {
            "username": username,
            "device_name": device_name,
            "started_at": time.time(),
        }


def _release_device_scan_lock(device_lock_id: str) -> None:
    with _DEVICE_SCAN_LOCK:
        _ACTIVE_DEVICE_SCANS.pop(device_lock_id, None)


def _build_scan_status_payload(requested_device_name: str | None = None) -> dict:
    config_manager = get_config_manager()
    username = config_manager.get_current_user()
    device_name = _resolve_requested_device_name(
        config_manager,
        username,
        requested_device_name,
    )
    configured_device_id, scanimage_device_name = _resolve_scan_device_details(
        username,
        device_name,
    )
    device_lock_id = _resolve_scan_lock_device_id(
        username,
        device_name,
        configured_device_id,
        scanimage_device_name,
    )

    with _DEVICE_SCAN_LOCK:
        active_scan = _ACTIVE_DEVICE_SCANS.get(device_lock_id)

    payload = {
        "status": "ok",
        "in_progress": active_scan is not None,
        "username": username,
        "device_name": device_name,
        "device_id": configured_device_id,
        "scanimage_device_name": scanimage_device_name,
        "device_lock_id": device_lock_id,
    }

    if active_scan is not None:
        payload["active_scan"] = active_scan

    return payload


def _process_scan_with_device_lock(
    progress_callback=None, requested_device_name: str | None = None
) -> dict:
    config_manager = get_config_manager()
    username = config_manager.get_current_user()
    device_name = _resolve_requested_device_name(
        config_manager,
        username,
        requested_device_name,
    )
    configured_device_id, scanimage_device_name = _resolve_scan_device_details(
        username,
        device_name,
    )
    device_lock_id = _resolve_scan_lock_device_id(
        username,
        device_name,
        configured_device_id,
        scanimage_device_name,
    )

    _acquire_device_scan_lock(device_lock_id, username, device_name)
    try:
        return _process_scan(
            progress_callback=progress_callback,
            requested_device_name=device_name,
        )
    finally:
        _release_device_scan_lock(device_lock_id)


def _build_device_payload(
    config_manager: ConfigManager, username: str, device_name: str
) -> dict:
    device_settings = config_manager.get_user_device(username, device_name)
    configured_device_id = device_settings.get("device_id")
    scanimage_device_name = None
    if configured_device_id is not None:
        scanimage_device_name = _resolve_libusb_device_id(configured_device_id)
    effective_scan_timeout_seconds = _resolve_scan_timeout_seconds(username, device_name)

    return {
        "device_name": device_name,
        "device_id": configured_device_id,
        "scanimage_device_name": scanimage_device_name,
        "scan_command": device_settings.get("scan_command"),
        "scan_output_mode": device_settings.get("scan_output_mode"),
        "scan_timeout_seconds": device_settings.get("scan_timeout_seconds"),
        "effective_scan_timeout_seconds": effective_scan_timeout_seconds,
        "scanimage_params": config_manager.get_device_scanimage_params(
            username, device_name
        ),
    }


def _build_device_configurations_payload() -> dict:
    config_manager = get_config_manager()
    username = config_manager.get_current_user()
    device_names = config_manager.list_user_devices(username)
    selected_device_name = config_manager.get_active_device_name(username)
    raw_paperless_base_url = config_manager.get_paperless_base_url()
    paperless_base_url = ""
    if isinstance(raw_paperless_base_url, str):
        paperless_base_url = raw_paperless_base_url.strip().rstrip("/")
    devices = [
        _build_device_payload(config_manager, username, device_name)
        for device_name in device_names
    ]

    return {
        "status": "ok",
        "username": username,
        "selected_device_name": selected_device_name,
        "paperless_base_url": paperless_base_url,
        "devices": devices,
    }


def _resolve_requested_device_name(
    config_manager: ConfigManager,
    username: str,
    requested_device_name: str | None,
) -> str | None:
    configured_device_names = config_manager.list_user_devices(username)
    if requested_device_name is None:
        return config_manager.get_active_device_name(username)

    if requested_device_name in configured_device_names:
        return requested_device_name

    raise RuntimeError(
        f"Device '{requested_device_name}' is not configured for user '{username}'."
    )


def _parse_scan_progress_line(raw_line: str) -> dict | None:
    line = raw_line.strip()
    if line == "":
        return None

    scanning_page_match = re.search(r"Scanning page\s+(\d+)", line, re.IGNORECASE)
    if scanning_page_match:
        page_number = int(scanning_page_match.group(1))
        return {
            "status": "scanning",
            "message": f"Scanning page {page_number}",
            "page_count": max(page_number - 1, 0),
        }

    scanned_page_match = re.search(r"Scanned page\s+(\d+)", line, re.IGNORECASE)
    if scanned_page_match:
        page_number = int(scanned_page_match.group(1))
        return {
            "status": "scanning",
            "message": f"Scanned page {page_number}",
            "page_count": page_number,
        }

    batch_terminated_match = re.search(
        r"Batch terminated,\s*(\d+)\s*pages scanned", line, re.IGNORECASE
    )
    if batch_terminated_match:
        page_count = int(batch_terminated_match.group(1))
        return {
            "status": "scanning",
            "message": f"Batch terminated, {page_count} pages scanned",
            "page_count": page_count,
        }

    return {
        "status": "scanning",
        "message": line,
    }


def _run_scan_command(
    batch_output_pattern: Path,
    progress_callback=None,
    username: str | None = None,
    device_name: str | None = None,
) -> list[Path]:
    command = _build_scan_command(batch_output_pattern, username, device_name)
    scan_timeout_seconds_per_page = _resolve_scan_timeout_seconds(username, device_name)

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Scan command not found. Configure scan_command in config.ini or install scanimage."
        ) from exc

    if process.stderr is None:
        process.kill()
        raise RuntimeError("Failed to capture scanner progress output.")

    stderr_messages = []
    last_page_progress_at = time.monotonic()
    while True:
        ready_streams, _, _ = select.select(
            [process.stderr], [], [], 1
        )
        if not ready_streams:
            elapsed_without_page_progress = time.monotonic() - last_page_progress_at
            if elapsed_without_page_progress > scan_timeout_seconds_per_page:
                process.kill()
                process.wait()
                raise RuntimeError(
                    f"Scan command timed out after {scan_timeout_seconds_per_page} seconds without page progress."
                )
            continue

        line = process.stderr.readline()
        if line == "":
            if process.poll() is not None:
                break
            continue

        stripped_line = line.strip()
        if stripped_line != "":
            stderr_messages.append(stripped_line)

        if progress_callback is not None:
            progress_update = _parse_scan_progress_line(line)
            if progress_update is not None:
                progress_callback(progress_update)
                if "page_count" in progress_update:
                    last_page_progress_at = time.monotonic()

    return_code = process.wait()
    if return_code != 0:
        stderr_message = "\n".join(stderr_messages[-3:]).strip()
        if not stderr_message:
            stderr_message = "scanner command exited with a non-zero status"
        raise RuntimeError(f"Scanner command failed: {stderr_message}")

    scan_output_mode = _resolve_scan_output_mode(username, device_name)
    if scan_output_mode == "single_file":
        output_tiff_paths = [_build_single_output_tiff_path(batch_output_pattern)]
    else:
        batch_stem = batch_output_pattern.stem.replace("%d", "")
        output_tiff_paths = list(batch_output_pattern.parent.glob(f"{batch_stem}*.tiff"))

    def _extract_batch_index(path: Path) -> int:
        match = re.search(r"(\d+)(?=\.tiff$)", path.name)
        if match is None:
            return -1
        return int(match.group(1))

    output_tiff_paths = sorted(output_tiff_paths, key=lambda path: (_extract_batch_index(path), path.name))
    if not output_tiff_paths:
        raise RuntimeError("Scanner produced no TIFF output.")

    empty_output_files = [
        output_tiff_path.name
        for output_tiff_path in output_tiff_paths
        if output_tiff_path.stat().st_size == 0
    ]
    if empty_output_files:
        empty_files_summary = ", ".join(empty_output_files[:5])
        if len(empty_output_files) > 5:
            empty_files_summary = f"{empty_files_summary}, ..."
        raise RuntimeError(
            f"Scanner produced empty TIFF output file(s): {empty_files_summary}."
        )

    return output_tiff_paths


def _convert_tiffs_to_pdf(input_tiff_paths: list[Path], output_pdf_path: Path) -> int:
    if Image is None:
        raise RuntimeError(
            "PIL is not installed. Install Pillow via pip or install python3-pil and run with system site-packages."
        )

    try:
        converted_frames = []
        for input_tiff_path in input_tiff_paths:
            with Image.open(input_tiff_path) as image:
                frame_count = getattr(image, "n_frames", 1)
                for frame_index in range(frame_count):
                    image.seek(frame_index)
                    converted_frames.append(image.convert("RGB"))
    except FileNotFoundError as exc:
        raise RuntimeError("A TIFF file is missing for PDF conversion.") from exc
    except UnidentifiedImageError as exc:
        raise RuntimeError("Scanner output contains an invalid TIFF image.") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to read TIFF outputs: {exc}") from exc

    if not converted_frames:
        raise RuntimeError("TIFF output contains no pages.")

    first_page, *remaining_pages = converted_frames
    try:
        first_page.save(
            output_pdf_path,
            format="PDF",
            save_all=True,
            append_images=remaining_pages,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to convert TIFF to PDF: {exc}") from exc

    if not output_pdf_path.exists() or output_pdf_path.stat().st_size == 0:
        raise RuntimeError("Generated PDF is empty.")

    return len(converted_frames)


def _build_paperless_upload_url(username: str) -> str:
    base_url = get_config_manager().get_paperless_base_url().strip().rstrip("/")
    if not base_url:
        raise RuntimeError("global.paperless_base_url is not configured.")
    return f"{base_url}/api/documents/post_document/"


def _extract_paperless_task_id(paperless_response: dict | None) -> str | None:
    if not isinstance(paperless_response, dict):
        return None

    for key in ["task_id", "task", "task_uuid"]:
        value = paperless_response.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()

    raw_response = paperless_response.get("raw_response")
    if isinstance(raw_response, str) and raw_response.strip() != "":
        return raw_response.strip()

    return None


def _build_paperless_task_url(task_id: str) -> str:
    base_url = get_config_manager().get_paperless_base_url().strip().rstrip("/")
    if not base_url:
        raise RuntimeError("global.paperless_base_url is not configured.")
    return f"{base_url}/api/tasks/?task_id={task_id}"


def _normalize_paperless_task_payload(task_id: str, task_payload: dict | None) -> dict:
    task_payload = task_payload if isinstance(task_payload, dict) else {}
    related_document = task_payload.get("related_document")
    if related_document is not None:
        related_document = str(related_document)

    result = task_payload.get("result")
    if result is not None:
        result = str(result)

    date_done = task_payload.get("date_done")
    if date_done is not None:
        date_done = str(date_done)

    task_file_name = task_payload.get("task_file_name")
    if task_file_name is not None:
        task_file_name = str(task_file_name)

    return {
        "status": "ok",
        "task_id": task_id,
        "task_status": task_payload.get("status"),
        "related_document": related_document,
        "result": result,
        "date_done": date_done,
        "task_file_name": task_file_name,
        "raw_task": task_payload,
    }


def _fetch_paperless_task_status(task_id: str, username: str | None = None) -> dict:
    if username is None:
        raise RuntimeError("username is required for Paperless task status lookup.")

    api_token = get_config_manager().get_user_token(username)
    if not api_token:
        raise RuntimeError(f"No paperless API token configured for user '{username}' in config.ini.")

    task_url = _build_paperless_task_url(task_id)
    headers = {"Authorization": f"Token {api_token}"}

    try:
        response = requests.get(
            task_url,
            headers=headers,
            timeout=15,
        )
    except requests.Timeout as exc:
        raise RuntimeError("Paperless task status request timed out.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Paperless task status request failed: {exc}") from exc

    if response.status_code >= 400:
        response_body = response.text.strip()
        if len(response_body) > 300:
            response_body = f"{response_body[:300]}..."
        if not response_body:
            response_body = response.reason or "unknown Paperless error"
        raise RuntimeError(
            f"Paperless task status failed ({response.status_code}): {response_body}"
        )

    try:
        parsed_body = response.json()
    except ValueError as exc:
        raise RuntimeError("Paperless task status response was not valid JSON.") from exc

    tasks = []
    if isinstance(parsed_body, list):
        tasks = parsed_body
    elif isinstance(parsed_body, dict):
        maybe_results = parsed_body.get("results")
        if isinstance(maybe_results, list):
            tasks = maybe_results

    for task_payload in tasks:
        if not isinstance(task_payload, dict):
            continue
        payload_task_id = task_payload.get("task_id")
        if payload_task_id is None or str(payload_task_id) == task_id:
            return _normalize_paperless_task_payload(task_id, task_payload)

    raise LookupError("Task not found")


def _calculate_paperless_timeout_seconds(page_count: int, username: str | None = None) -> int:
    timeout_per_page_seconds = None
    if username is not None:
        timeout_per_page_seconds = get_config_manager().get_paperless_timeout_seconds()
    if timeout_per_page_seconds is None:
        timeout_per_page_seconds = 5
    internal_overhead_seconds = 10
    return internal_overhead_seconds + (
        timeout_per_page_seconds * max(page_count, 1)
    )


def _resolve_scan_timeout_seconds(username: str | None, device_name: str | None = None) -> int:
    scan_timeout_seconds_per_page = None
    if username is not None:
        scan_timeout_seconds_per_page = get_config_manager().get_device_scan_timeout_seconds(
            username, device_name
        )
    if not isinstance(scan_timeout_seconds_per_page, int) or scan_timeout_seconds_per_page <= 0:
        return 30
    return scan_timeout_seconds_per_page


def _build_timing_metrics(
    total_seconds: float,
    scan_seconds: float,
    paperless_seconds: float,
    page_count: int,
) -> dict:
    effective_page_count = max(page_count, 1)
    return {
        "total_seconds": round(total_seconds, 3),
        "scan_seconds": round(scan_seconds, 3),
        "paperless_seconds": round(paperless_seconds, 3),
        "scan_seconds_per_page": round(scan_seconds / effective_page_count, 3),
        "paperless_seconds_per_page": round(paperless_seconds / effective_page_count, 3),
    }


def _upload_pdf_to_paperless(pdf_path: Path, page_count: int, username: str | None = None) -> dict:
    if username is None:
        raise RuntimeError("username is required for Paperless upload.")

    api_token = get_config_manager().get_user_token(username)
    if not api_token:
        raise RuntimeError(f"No paperless API token configured for user '{username}' in config.ini.")

    upload_url = _build_paperless_upload_url(username)
    upload_timeout_seconds = _calculate_paperless_timeout_seconds(page_count, username)

    headers = {"Authorization": f"Token {api_token}"}

    response = None
    for attempt in range(1, _PAPERLESS_UPLOAD_MAX_ATTEMPTS + 1):
        try:
            with pdf_path.open("rb") as pdf_file:
                response = requests.post(
                    upload_url,
                    headers=headers,
                    files={"document": (pdf_path.name, pdf_file, "application/pdf")},
                    timeout=upload_timeout_seconds,
                )
        except requests.RequestException as exc:
            if attempt >= _PAPERLESS_UPLOAD_MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Paperless upload request failed: {exc}"
                ) from exc

            retry_delay_seconds = _PAPERLESS_UPLOAD_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            time.sleep(retry_delay_seconds)
            continue

        if response.status_code >= 400:
            response_body = response.text.strip()
            if len(response_body) > 300:
                response_body = f"{response_body[:300]}..."
            if not response_body:
                response_body = response.reason or "unknown Paperless error"

            if (
                response.status_code in _PAPERLESS_RETRYABLE_STATUS_CODES
                and attempt < _PAPERLESS_UPLOAD_MAX_ATTEMPTS
            ):
                retry_delay_seconds = _PAPERLESS_UPLOAD_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                time.sleep(retry_delay_seconds)
                continue

            raise RuntimeError(
                f"Paperless upload failed ({response.status_code}): {response_body}"
            )

        break

    if response is None:
        raise RuntimeError("Paperless upload failed before receiving a response.")

    try:
        parsed_body = response.json()
    except ValueError:
        parsed_body = {}

    if isinstance(parsed_body, dict):
        return parsed_body
    if isinstance(parsed_body, str):
        parsed_value = parsed_body.strip()
        if parsed_value:
            return {"raw_response": parsed_value, "task_id": parsed_value}
    return {}


def _process_scan(progress_callback=None, requested_device_name: str | None = None) -> dict:
    config_manager = get_config_manager()
    username = config_manager.get_current_user()
    device_name = _resolve_requested_device_name(
        config_manager,
        username,
        requested_device_name,
    )
    configured_device_id, scanimage_device_name = _resolve_scan_device_details(
        username, device_name
    )
    scan_timeout_seconds = _resolve_scan_timeout_seconds(username, device_name)
    total_started_at = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="scanexpress-") as working_dir:
        working_dir_path = Path(working_dir)
        batch_output_pattern = working_dir_path / "scan_output%d.tiff"
        pdf_path = working_dir_path / "scan_output.pdf"

        if progress_callback is not None:
            progress_callback(
                {
                    "status": "scanning",
                    "message": "Starting scan...",
                    "scan_timeout_seconds": scan_timeout_seconds,
                    "timeout_countdown_start_seconds": _TIMEOUT_COUNTDOWN_START_SECONDS,
                }
            )

        scan_started_at = time.monotonic()
        tiff_paths = _run_scan_command(
            batch_output_pattern,
            progress_callback,
            username,
            device_name,
        )
        scan_elapsed_seconds = time.monotonic() - scan_started_at

        if progress_callback is not None:
            progress_callback(
                {
                    "status": "processing",
                    "message": f"Converting {len(tiff_paths)} TIFF file(s) to PDF...",
                }
            )

        page_count = _convert_tiffs_to_pdf(tiff_paths, pdf_path)

        if progress_callback is not None:
            paperless_timeout_seconds = _calculate_paperless_timeout_seconds(page_count, username)
            progress_callback(
                {
                    "status": "uploading",
                    "message": f"Uploading {page_count} page(s) to Paperless-ngx...",
                    "page_count": page_count,
                    "paperless_timeout_seconds": paperless_timeout_seconds,
                    "timeout_countdown_start_seconds": _TIMEOUT_COUNTDOWN_START_SECONDS,
                }
            )

        paperless_started_at = time.monotonic()
        paperless_response = _upload_pdf_to_paperless(pdf_path, page_count, username)
        paperless_elapsed_seconds = time.monotonic() - paperless_started_at

    total_elapsed_seconds = time.monotonic() - total_started_at
    timing_metrics = _build_timing_metrics(
        total_elapsed_seconds,
        scan_elapsed_seconds,
        paperless_elapsed_seconds,
        page_count,
    )

    document_id = paperless_response.get("id")
    paperless_task_id = _extract_paperless_task_id(paperless_response)
    message = f"Scan uploaded to Paperless-ngx. pages={page_count}"
    message = (
        f"{message} total={timing_metrics['total_seconds']}s"
        f" scan={timing_metrics['scan_seconds']}s"
        f" paperless={timing_metrics['paperless_seconds']}s"
        f" scan_per_page={timing_metrics['scan_seconds_per_page']}s"
        f" paperless_per_page={timing_metrics['paperless_seconds_per_page']}s"
    )
    if document_id is not None:
        message = f"{message} document_id={document_id}"

    return {
        "status": "ok",
        "message": message,
        "document_id": document_id,
        "page_count": page_count,
        "username": username,
        "device_name": device_name,
        "device_id": configured_device_id,
        "scanimage_device_name": scanimage_device_name,
        "timing_metrics": timing_metrics,
        "paperless_task_id": paperless_task_id,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/scan")
def trigger_scan():
    request_json = request.get_json(silent=True) or {}
    requested_device_name = request_json.get("device_name")
    if requested_device_name is not None and not isinstance(requested_device_name, str):
        return (
            jsonify({"status": "error", "message": "device_name must be a string."}),
            400,
        )

    try:
        return (
            jsonify(_process_scan_with_device_lock(requested_device_name=requested_device_name)),
            200,
        )
    except ScanInProgressError as exc:
        return jsonify({"status": "busy", "message": str(exc)}), 409
    except RuntimeError as exc:
        if "not configured for user" in str(exc):
            return jsonify({"status": "error", "message": str(exc)}), 400
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception:
        app.logger.exception("Unexpected error while processing /api/scan")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Unexpected backend error while processing scan.",
                }
            ),
            500,
        )


@app.post("/api/scan/stream")
def trigger_scan_stream():
    request_json = request.get_json(silent=True) or {}
    requested_device_name = request_json.get("device_name")
    if requested_device_name is not None and not isinstance(requested_device_name, str):
        return (
            jsonify({"status": "error", "message": "device_name must be a string."}),
            400,
        )

    config_manager = get_config_manager()
    username = config_manager.get_current_user()
    try:
        device_name = _resolve_requested_device_name(
            config_manager,
            username,
            requested_device_name,
        )
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    configured_device_id, scanimage_device_name = _resolve_scan_device_details(
        username,
        device_name,
    )
    device_lock_id = _resolve_scan_lock_device_id(
        username,
        device_name,
        configured_device_id,
        scanimage_device_name,
    )

    with _DEVICE_SCAN_LOCK:
        if device_lock_id in _ACTIVE_DEVICE_SCANS:
            return (
                jsonify(
                    {
                        "status": "busy",
                        "message": f"Scan already in progress for device_id '{device_lock_id}'.",
                    }
                ),
                409,
            )

    @stream_with_context
    def stream_scan_updates():
        updates_queue: Queue[dict | None] = Queue()

        def send_progress(update: dict) -> None:
            updates_queue.put(update)

        def worker() -> None:
            try:
                result = _process_scan_with_device_lock(
                    send_progress,
                    requested_device_name=device_name,
                )
                updates_queue.put({**result, "complete": True})
            except ScanInProgressError as exc:
                updates_queue.put(
                    {
                        "status": "busy",
                        "message": str(exc),
                        "complete": True,
                    }
                )
            except RuntimeError as exc:
                updates_queue.put(
                    {
                        "status": "error",
                        "message": str(exc),
                        "complete": True,
                    }
                )
            except Exception:
                app.logger.exception("Unexpected error while processing /api/scan/stream")
                updates_queue.put(
                    {
                        "status": "error",
                        "message": "Unexpected backend error while processing scan.",
                        "complete": True,
                    }
                )
            finally:
                updates_queue.put(None)

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        while True:
            update = updates_queue.get()
            if update is None:
                break
            yield f"{json.dumps(update)}\n"

    return Response(stream_scan_updates(), mimetype="application/x-ndjson")


@app.get("/api/device-configurations")
def list_device_configurations():
    try:
        return jsonify(_build_device_configurations_payload()), 200
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception:
        app.logger.exception("Unexpected error while processing /api/device-configurations")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Unexpected backend error while loading device configurations.",
                }
            ),
            500,
        )


@app.get("/api/scan/status")
def get_scan_status():
    requested_device_name = request.args.get("device_name")
    if requested_device_name is not None and not isinstance(requested_device_name, str):
        return (
            jsonify({"status": "error", "message": "device_name must be a string."}),
            400,
        )

    try:
        return jsonify(_build_scan_status_payload(requested_device_name)), 200
    except RuntimeError as exc:
        if "not configured for user" in str(exc):
            return jsonify({"status": "error", "message": str(exc)}), 400
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception:
        app.logger.exception("Unexpected error while processing /api/scan/status")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Unexpected backend error while loading scan status.",
                }
            ),
            500,
        )


@app.get("/api/paperless/tasks/<task_id>")
def get_paperless_task_status(task_id: str):
    if task_id.strip() == "":
        return jsonify({"status": "error", "message": "task_id is required."}), 400

    try:
        config_manager = get_config_manager()
        username = config_manager.get_current_user()
        payload = _fetch_paperless_task_status(task_id, username)
        return jsonify(payload), 200
    except LookupError:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 502
    except Exception:
        app.logger.exception("Unexpected error while processing /api/paperless/tasks/<task_id>")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Unexpected backend error while loading Paperless task status.",
                }
            ),
            500,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
