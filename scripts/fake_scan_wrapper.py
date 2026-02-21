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


def main() -> int:
    mode = _read_mode()

    if mode == "fail":
        sys.stderr.write("fake scanner forced failure\n")
        return 2

    if mode == "empty":
        return 0

    if mode == "adf":
        first_page = Image.new("RGB", (16, 16), "white")
        second_page = Image.new("RGB", (16, 16), "lightgray")
        third_page = Image.new("RGB", (16, 16), "silver")
        output_buffer = io.BytesIO()
        first_page.save(
            output_buffer,
            format="TIFF",
            save_all=True,
            append_images=[second_page, third_page],
        )
        sys.stdout.buffer.write(output_buffer.getvalue())
        sys.stdout.buffer.flush()
        return 0

    image = Image.new("RGB", (16, 16), "white")
    output_buffer = io.BytesIO()
    image.save(output_buffer, format="TIFF")

    sys.stdout.buffer.write(output_buffer.getvalue())
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
