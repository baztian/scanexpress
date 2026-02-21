import json
import os
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
from flask import Flask, Response, jsonify, render_template, stream_with_context

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    Image = None
    UnidentifiedImageError = OSError

app = Flask(__name__)


def _read_positive_int_env(name: str, default_value: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default_value

    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc

    if parsed_value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")

    return parsed_value


def _build_scan_command(batch_output_pattern: Path) -> list[str]:
    configured_command = os.getenv("SCANEXPRESS_SCAN_COMMAND")
    if configured_command and configured_command.strip() != "":
        command = shlex.split(configured_command)
    else:
        command = ["scanimage"]

    scanner_device = os.getenv("SCANEXPRESS_SCANNER_DEVICE", "").strip()
    if scanner_device:
        command.extend(["-d", scanner_device])
    command.append("--format=tiff")
    command.append(f"--batch={batch_output_pattern}")
    return command


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
    batch_output_pattern: Path, progress_callback=None
) -> list[Path]:
    command = _build_scan_command(batch_output_pattern)
    scan_timeout_seconds_per_page = _read_positive_int_env(
        "SCANEXPRESS_SCAN_TIMEOUT_SECONDS", 30
    )

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
            "Scan command not found. Configure SCANEXPRESS_SCAN_COMMAND or install scanimage."
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
            if time.monotonic() - last_page_progress_at > scan_timeout_seconds_per_page:
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


def _build_paperless_upload_url() -> str:
    base_url = os.getenv("SCANEXPRESS_PAPERLESS_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("SCANEXPRESS_PAPERLESS_BASE_URL is not configured.")
    return f"{base_url}/api/documents/post_document/"


def _calculate_paperless_timeout_seconds(page_count: int) -> int:
    timeout_per_page_seconds = _read_positive_int_env(
        "SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS", 5
    )
    internal_overhead_seconds = 10
    return internal_overhead_seconds + (
        timeout_per_page_seconds * max(page_count, 1)
    )


def _upload_pdf_to_paperless(pdf_path: Path, page_count: int) -> dict:
    api_token = os.getenv("SCANEXPRESS_PAPERLESS_API_TOKEN", "").strip()
    if not api_token:
        raise RuntimeError("SCANEXPRESS_PAPERLESS_API_TOKEN is not configured.")

    upload_url = _build_paperless_upload_url()
    upload_timeout_seconds = _calculate_paperless_timeout_seconds(page_count)

    headers = {"Authorization": f"Token {api_token}"}

    try:
        with pdf_path.open("rb") as pdf_file:
            response = requests.post(
                upload_url,
                headers=headers,
                files={"document": (pdf_path.name, pdf_file, "application/pdf")},
                timeout=upload_timeout_seconds,
            )
    except requests.RequestException as exc:
        raise RuntimeError(f"Paperless upload request failed: {exc}") from exc

    if response.status_code >= 400:
        response_body = response.text.strip()
        if len(response_body) > 300:
            response_body = f"{response_body[:300]}..."
        if not response_body:
            response_body = response.reason or "unknown Paperless error"
        raise RuntimeError(
            f"Paperless upload failed ({response.status_code}): {response_body}"
        )

    try:
        parsed_body = response.json()
    except ValueError:
        parsed_body = {}

    if isinstance(parsed_body, dict):
        return parsed_body
    return {}


def _process_scan(progress_callback=None) -> dict:
    with tempfile.TemporaryDirectory(prefix="scanexpress-") as working_dir:
        working_dir_path = Path(working_dir)
        batch_output_pattern = working_dir_path / "scan_output%d.tiff"
        pdf_path = working_dir_path / "scan_output.pdf"

        if progress_callback is not None:
            progress_callback({"status": "scanning", "message": "Starting scan..."})

        tiff_paths = _run_scan_command(batch_output_pattern, progress_callback)

        if progress_callback is not None:
            progress_callback(
                {
                    "status": "processing",
                    "message": f"Converting {len(tiff_paths)} TIFF file(s) to PDF...",
                }
            )

        page_count = _convert_tiffs_to_pdf(tiff_paths, pdf_path)

        if progress_callback is not None:
            progress_callback(
                {
                    "status": "uploading",
                    "message": f"Uploading {page_count} page(s) to Paperless-ngx...",
                    "page_count": page_count,
                }
            )

        paperless_response = _upload_pdf_to_paperless(pdf_path, page_count)

    document_id = paperless_response.get("id")
    message = f"Scan uploaded to Paperless-ngx. pages={page_count}"
    if document_id is not None:
        message = f"{message} document_id={document_id}"

    return {
        "status": "ok",
        "message": message,
        "document_id": document_id,
        "page_count": page_count,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/scan")
def trigger_scan():
    try:
        return jsonify(_process_scan()), 200
    except RuntimeError as exc:
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
    @stream_with_context
    def stream_scan_updates():
        updates_queue: Queue[dict | None] = Queue()

        def send_progress(update: dict) -> None:
            updates_queue.put(update)

        def worker() -> None:
            try:
                result = _process_scan(send_progress)
                updates_queue.put({**result, "complete": True})
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
