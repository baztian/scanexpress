#!/usr/bin/env python3
import io
import os
import sys
from pathlib import Path

from PIL import Image


def _read_mode() -> str:
    mode_file = os.getenv("SCANEXPRESS_FAKE_SCAN_MODE_FILE", "").strip()
    if not mode_file:
        return "success"

    path = Path(mode_file)
    if not path.exists():
        return "success"

    return path.read_text(encoding="utf-8").strip().lower() or "success"


def _read_batch_pattern() -> str | None:
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg.startswith("--batch="):
            return arg.split("=", 1)[1]
        if arg == "--batch" and index + 1 < len(args):
            return args[index + 1]
    return None


def _build_tiff_bytes(color: str) -> bytes:
    image = Image.new("RGB", (16, 16), color)
    output_buffer = io.BytesIO()
    image.save(output_buffer, format="TIFF")
    return output_buffer.getvalue()


def _write_batch_outputs(batch_pattern: str, pages: list[bytes]) -> None:
    for page_index, page_bytes in enumerate(pages, start=1):
        page_path = Path(batch_pattern.replace("%d", str(page_index)))
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(page_bytes)


def main() -> int:
    mode = _read_mode()
    batch_pattern = _read_batch_pattern()

    if mode == "fail":
        sys.stderr.write("fake scanner forced failure\n")
        return 2

    if mode == "empty":
        return 0

    if mode == "adf":
        pages = [
            _build_tiff_bytes("white"),
            _build_tiff_bytes("lightgray"),
            _build_tiff_bytes("silver"),
        ]
        if batch_pattern:
            _write_batch_outputs(batch_pattern, pages)
            return 0

        output_buffer = io.BytesIO()
        first_page = Image.new("RGB", (16, 16), "white")
        second_page = Image.new("RGB", (16, 16), "lightgray")
        third_page = Image.new("RGB", (16, 16), "silver")
        first_page.save(output_buffer, format="TIFF", save_all=True, append_images=[second_page, third_page])
        sys.stdout.buffer.write(output_buffer.getvalue())
        sys.stdout.buffer.flush()
        return 0

    single_page = _build_tiff_bytes("white")
    if batch_pattern:
        _write_batch_outputs(batch_pattern, [single_page])
        return 0

    sys.stdout.buffer.write(single_page)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
