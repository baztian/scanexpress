import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template

try:
    from PIL import Image, ImageSequence, UnidentifiedImageError
except ImportError:
    Image = None
    ImageSequence = None
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


def _build_scan_command() -> list[str]:
    configured_command = os.getenv("SCANEXPRESS_SCAN_COMMAND")
    if configured_command and configured_command.strip() != "":
        command = shlex.split(configured_command)
    else:
        command = ["scanimage"]

    scanner_device = os.getenv("SCANEXPRESS_SCANNER_DEVICE", "").strip()
    if scanner_device:
        command.extend(["-d", scanner_device])
    command.append("--format=tiff")
    return command


def _run_scan_command(output_tiff_path: Path) -> None:
    command = _build_scan_command()
    scan_timeout_seconds = _read_positive_int_env(
        "SCANEXPRESS_SCAN_TIMEOUT_SECONDS", 60
    )

    try:
        with output_tiff_path.open("wb") as output_file:
            result = subprocess.run(
                command,
                stdout=output_file,
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

    if not output_tiff_path.exists() or output_tiff_path.stat().st_size == 0:
        raise RuntimeError("Scanner produced no TIFF output.")


def _convert_tiff_to_pdf(input_tiff_path: Path, output_pdf_path: Path) -> None:
    if Image is None or ImageSequence is None:
        raise RuntimeError(
            "PIL is not installed. Install Pillow via pip or install python3-pil and run with system site-packages."
        )

    try:
        with Image.open(input_tiff_path) as image:
            converted_frames = [
                frame.convert("RGB") for frame in ImageSequence.Iterator(image)
            ]
    except FileNotFoundError as exc:
        raise RuntimeError("TIFF file not found for PDF conversion.") from exc
    except UnidentifiedImageError as exc:
        raise RuntimeError("Scanner output is not a valid TIFF image.") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to read TIFF output: {exc}") from exc

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
            tiff_path = working_dir_path / "scan_output.tiff"
            pdf_path = working_dir_path / "scan_output.pdf"

            _run_scan_command(tiff_path)
            _convert_tiff_to_pdf(tiff_path, pdf_path)
            paperless_response = _upload_pdf_to_paperless(pdf_path)

        document_id = paperless_response.get("id")
        message = "Scan uploaded to Paperless-ngx."
        if document_id is not None:
            message = f"{message} document_id={document_id}"

        return (
            jsonify(
                {
                    "status": "ok",
                    "message": message,
                    "document_id": document_id,
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
