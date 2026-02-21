import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template

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


def _run_scan_command(batch_output_pattern: Path) -> list[Path]:
    command = _build_scan_command(batch_output_pattern)
    scan_timeout_seconds = _read_positive_int_env(
        "SCANEXPRESS_SCAN_TIMEOUT_SECONDS", 60
    )

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=scan_timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Scan command not found. Configure SCANEXPRESS_SCAN_COMMAND or install scanimage."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Scan command timed out after {scan_timeout_seconds} seconds."
        ) from exc

    if result.returncode != 0:
        stderr_message = result.stderr.decode("utf-8", errors="replace").strip()
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


def _upload_pdf_to_paperless(pdf_path: Path) -> dict:
    api_token = os.getenv("SCANEXPRESS_PAPERLESS_API_TOKEN", "").strip()
    if not api_token:
        raise RuntimeError("SCANEXPRESS_PAPERLESS_API_TOKEN is not configured.")

    upload_url = _build_paperless_upload_url()
    upload_timeout_seconds = _read_positive_int_env(
        "SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS", 60
    )

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


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/scan")
def trigger_scan():
    try:
        with tempfile.TemporaryDirectory(prefix="scanexpress-") as working_dir:
            working_dir_path = Path(working_dir)
            batch_output_pattern = working_dir_path / "scan_output%d.tiff"
            pdf_path = working_dir_path / "scan_output.pdf"

            tiff_paths = _run_scan_command(batch_output_pattern)
            page_count = _convert_tiffs_to_pdf(tiff_paths, pdf_path)
            paperless_response = _upload_pdf_to_paperless(pdf_path)

        document_id = paperless_response.get("id")
        message = f"Scan uploaded to Paperless-ngx. pages={page_count}"
        if document_id is not None:
            message = f"{message} document_id={document_id}"

        return (
            jsonify(
                {
                    "status": "ok",
                    "message": message,
                    "document_id": document_id,
                    "page_count": page_count,
                }
            ),
            200,
        )
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
