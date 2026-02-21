import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as scan_app


class BatchScanCommandTests(unittest.TestCase):
    @patch("app.time.monotonic")
    @patch("app.select.select")
    @patch("app.subprocess.Popen")
    def test_run_scan_command_returns_batch_files_in_numeric_order(
        self, mock_popen, mock_select, mock_monotonic
    ):
        mock_monotonic.side_effect = [0, 1, 2, 3, 4]
        process = FakeProcess(
            stderr_lines=[
                "Scanning page 1\n",
                "Scanned page 1. (scanner status = 5)\n",
                "Batch terminated, 1 pages scanned\n",
            ],
            returncode=0,
        )
        mock_popen.return_value = process
        mock_select.side_effect = lambda streams, _w, _x, _timeout: (
            (streams, [], []) if not process.is_complete else (streams, [], [])
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for filename in ["scan_output10.tiff", "scan_output2.tiff", "scan_output1.tiff"]:
                (temp_path / filename).write_bytes(b"fake-tiff")

            result_paths = scan_app._run_scan_command(temp_path / "scan_output%d.tiff")

        self.assertEqual(
            [path.name for path in result_paths],
            ["scan_output1.tiff", "scan_output2.tiff", "scan_output10.tiff"],
        )

    @patch("app.time.monotonic")
    @patch("app.select.select")
    @patch("app.subprocess.Popen")
    def test_run_scan_command_rejects_empty_batch_output(
        self, mock_popen, mock_select, mock_monotonic
    ):
        mock_monotonic.side_effect = [0, 1, 2, 3, 4]
        process = FakeProcess(
            stderr_lines=[
                "Scanning page 1\n",
                "Scanned page 1. (scanner status = 5)\n",
                "Batch terminated, 1 pages scanned\n",
            ],
            returncode=0,
        )
        mock_popen.return_value = process
        mock_select.side_effect = lambda streams, _w, _x, _timeout: (
            (streams, [], []) if not process.is_complete else (streams, [], [])
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "scan_output1.tiff").write_bytes(b"")

            with self.assertRaises(RuntimeError) as context:
                scan_app._run_scan_command(temp_path / "scan_output%d.tiff")

        self.assertIn("empty TIFF output file", str(context.exception))

    @patch("app.time.monotonic")
    @patch("app.select.select")
    @patch("app.subprocess.Popen")
    def test_run_scan_command_applies_per_page_progress_timeout(
        self, mock_popen, mock_select, mock_monotonic
    ):
        process = FakeProcess(stderr_lines=[], returncode=0)
        mock_popen.return_value = process
        mock_select.return_value = ([], [], [])
        mock_monotonic.side_effect = [0, 2]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch.dict("os.environ", {"SCANEXPRESS_SCAN_TIMEOUT_SECONDS": "1"}):
                with self.assertRaises(RuntimeError) as context:
                    scan_app._run_scan_command(temp_path / "scan_output%d.tiff")

        self.assertIn("timed out", str(context.exception))


class PaperlessTimeoutTests(unittest.TestCase):
    def test_calculate_paperless_timeout_uses_per_page_setting_with_overhead(self):
        with patch.dict("os.environ", {"SCANEXPRESS_PAPERLESS_TIMEOUT_SECONDS": "4"}):
            self.assertEqual(scan_app._calculate_paperless_timeout_seconds(3), 22)


@unittest.skipIf(scan_app.Image is None, "Pillow is required for conversion tests")
class BatchTiffConversionTests(unittest.TestCase):
    def test_convert_tiffs_to_pdf_merges_files_and_counts_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tiff_paths = [
                temp_path / "scan_output1.tiff",
                temp_path / "scan_output2.tiff",
                temp_path / "scan_output3.tiff",
            ]
            colors = ["white", "lightgray", "silver"]

            for path, color in zip(tiff_paths, colors):
                image = scan_app.Image.new("RGB", (10, 10), color)
                image.save(path, format="TIFF")

            output_pdf_path = temp_path / "scan_output.pdf"
            page_count = scan_app._convert_tiffs_to_pdf(tiff_paths, output_pdf_path)

            self.assertEqual(page_count, 3)
            self.assertTrue(output_pdf_path.exists())
            self.assertGreater(output_pdf_path.stat().st_size, 0)


class FakeProcess:
    def __init__(self, stderr_lines: list[str], returncode: int):
        self._stderr_lines = iter(stderr_lines)
        self.stderr = self
        self.returncode = returncode
        self.is_complete = False
        self.was_killed = False

    def readline(self) -> str:
        try:
            return next(self._stderr_lines)
        except StopIteration:
            self.is_complete = True
            return ""

    def poll(self):
        if self.is_complete:
            return self.returncode
        return None

    def wait(self):
        self.is_complete = True
        return self.returncode

    def kill(self):
        self.was_killed = True
        self.is_complete = True


if __name__ == "__main__":
    unittest.main()
