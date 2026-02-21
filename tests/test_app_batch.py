import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as scan_app


class BatchScanCommandTests(unittest.TestCase):
    @patch("app.subprocess.run")
    def test_run_scan_command_returns_batch_files_in_numeric_order(self, mock_run):
        mock_run.return_value = subprocess_result(returncode=0, stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for filename in ["scan_output10.tiff", "scan_output2.tiff", "scan_output1.tiff"]:
                (temp_path / filename).write_bytes(b"fake-tiff")

            result_paths = scan_app._run_scan_command(temp_path / "scan_output%d.tiff")

        self.assertEqual(
            [path.name for path in result_paths],
            ["scan_output1.tiff", "scan_output2.tiff", "scan_output10.tiff"],
        )

    @patch("app.subprocess.run")
    def test_run_scan_command_rejects_empty_batch_output(self, mock_run):
        mock_run.return_value = subprocess_result(returncode=0, stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "scan_output1.tiff").write_bytes(b"")

            with self.assertRaises(RuntimeError) as context:
                scan_app._run_scan_command(temp_path / "scan_output%d.tiff")

        self.assertIn("empty TIFF output file", str(context.exception))


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


def subprocess_result(returncode: int, stderr: bytes):
    return type("Result", (), {"returncode": returncode, "stderr": stderr})()


if __name__ == "__main__":
    unittest.main()
