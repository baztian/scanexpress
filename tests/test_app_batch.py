import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app as scan_app


class BatchScanCommandTests(unittest.TestCase):
    def test_build_scan_command_adds_dynamic_scanimage_params(self):
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"
        fake_config_manager.get_device_scan_output_mode.return_value = "batch"
        fake_config_manager.get_device_scanimage_params.return_value = {
            "resolution": "300",
            "mode": "Gray",
            "contrast_adjustment": "10",
            "source": "Black & White",
        }

        with patch("app.get_config_manager", return_value=fake_config_manager):
            command = scan_app._build_scan_command(
                Path("/tmp/scan_output%d.tiff"),
                username="alice",
                device_name="brother-bw",
            )

        self.assertIn("-d", command)
        self.assertIn("BrotherADS2200:libusb:001:002", command)
        self.assertIn("--resolution", command)
        self.assertIn("300", command)
        self.assertIn("--mode", command)
        self.assertIn("Gray", command)
        self.assertIn("--contrast-adjustment", command)
        self.assertIn("10", command)
        self.assertIn("--source", command)
        self.assertIn("Black & White", command)
        source_index = command.index("--source")
        self.assertEqual(command[source_index + 1], "Black & White")
        self.assertIn("--format=tiff", command)
        self.assertIn("--batch=/tmp/scan_output%d.tiff", command)

    def test_build_scan_command_omits_device_flag_when_device_id_missing(self):
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = None
        fake_config_manager.get_device_scan_output_mode.return_value = "batch"
        fake_config_manager.get_device_scanimage_params.return_value = {"resolution": "300"}

        with patch("app.get_config_manager", return_value=fake_config_manager):
            command = scan_app._build_scan_command(
                Path("/tmp/scan_output%d.tiff"),
                username="alice",
                device_name="brother-bw",
            )

        self.assertNotIn("-d", command)
        self.assertIn("--resolution", command)
        self.assertIn("300", command)

    def test_build_scan_command_resolves_libusb_udev_symlink_to_bus_devnum(self):
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:/dev/brother-scanner"
        fake_config_manager.get_device_scan_output_mode.return_value = "batch"
        fake_config_manager.get_device_scanimage_params.return_value = {}

        with patch("app.get_config_manager", return_value=fake_config_manager), patch(
            "app.Path.resolve", return_value=Path("/dev/bus/usb/001/007")
        ):
            command = scan_app._build_scan_command(
                Path("/tmp/scan_output%d.tiff"),
                username="alice",
                device_name="brother-bw",
            )

        self.assertIn("-d", command)
        self.assertIn("BrotherADS2200:libusb:001:007", command)
        self.assertNotIn("BrotherADS2200:libusb:/dev/brother-scanner", command)

    def test_build_scan_command_keeps_device_id_when_udev_link_resolution_fails(self):
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:/dev/brother-scanner"
        fake_config_manager.get_device_scan_output_mode.return_value = "batch"
        fake_config_manager.get_device_scanimage_params.return_value = {}

        with patch("app.get_config_manager", return_value=fake_config_manager), patch(
            "app.Path.resolve", side_effect=FileNotFoundError
        ):
            command = scan_app._build_scan_command(
                Path("/tmp/scan_output%d.tiff"),
                username="alice",
                device_name="brother-bw",
            )

        self.assertIn("-d", command)
        self.assertIn("BrotherADS2200:libusb:/dev/brother-scanner", command)

    def test_resolve_scan_device_details_returns_configured_and_runtime_device_names(self):
        fake_config_manager = Mock()
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:/dev/brother-scanner"

        with patch("app.get_config_manager", return_value=fake_config_manager), patch(
            "app.Path.resolve", return_value=Path("/dev/bus/usb/001/007")
        ):
            configured_device_id, scanimage_device_name = scan_app._resolve_scan_device_details(
                "alice", "brother-bw"
            )

        self.assertEqual(configured_device_id, "BrotherADS2200:libusb:/dev/brother-scanner")
        self.assertEqual(scanimage_device_name, "BrotherADS2200:libusb:001:007")

    def test_build_scan_command_uses_output_file_for_single_file_mode(self):
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"
        fake_config_manager.get_device_scan_output_mode.return_value = "single_file"
        fake_config_manager.get_device_scanimage_params.return_value = {"resolution": "300"}

        with patch("app.get_config_manager", return_value=fake_config_manager):
            command = scan_app._build_scan_command(
                Path("/tmp/scan_output%d.tiff"),
                username="alice",
                device_name="flatbed",
            )

        self.assertIn("--format=tiff", command)
        self.assertIn("--output-file=/tmp/scan_output.tiff", command)
        self.assertNotIn("--batch=/tmp/scan_output%d.tiff", command)

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
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"
        fake_config_manager.get_device_scan_output_mode.return_value = "batch"
        fake_config_manager.get_device_scanimage_params.return_value = {}
        fake_config_manager.get_device_scan_timeout_seconds.return_value = 1

        with patch("app.get_config_manager", return_value=fake_config_manager):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with self.assertRaises(RuntimeError) as context:
                    scan_app._run_scan_command(
                        temp_path / "scan_output%d.tiff",
                        username="alice",
                        device_name="brother-bw",
                    )

        self.assertIn("timed out", str(context.exception))
        self.assertTrue(process.was_killed, "Process should be killed when timeout is reached")

    @patch("app.time.monotonic")
    @patch("app.select.select")
    @patch("app.subprocess.Popen")
    def test_run_scan_command_returns_single_output_file_for_single_file_mode(
        self, mock_popen, mock_select, mock_monotonic
    ):
        mock_monotonic.side_effect = [0, 1, 2, 3, 4]
        process = FakeProcess(
            stderr_lines=[
                "Scanning...\n",
            ],
            returncode=0,
        )
        mock_popen.return_value = process
        mock_select.side_effect = lambda streams, _w, _x, _timeout: (
            (streams, [], []) if not process.is_complete else (streams, [], [])
        )
        fake_config_manager = Mock()
        fake_config_manager.get_user_scan_command.return_value = "/usr/bin/scanimage"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"
        fake_config_manager.get_device_scan_output_mode.return_value = "single_file"
        fake_config_manager.get_device_scanimage_params.return_value = {}
        fake_config_manager.get_device_scan_timeout_seconds.return_value = 30

        with patch("app.get_config_manager", return_value=fake_config_manager):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / "scan_output.tiff").write_bytes(b"fake-tiff")

                result_paths = scan_app._run_scan_command(
                    temp_path / "scan_output%d.tiff",
                    username="alice",
                    device_name="flatbed",
                )

        self.assertEqual([path.name for path in result_paths], ["scan_output.tiff"])


class PaperlessTimeoutTests(unittest.TestCase):
    def test_calculate_paperless_timeout_uses_per_page_setting_with_overhead(self):
        fake_config_manager = Mock()
        fake_config_manager.get_paperless_timeout_seconds.return_value = 4
        with patch("app.get_config_manager", return_value=fake_config_manager):
            self.assertEqual(scan_app._calculate_paperless_timeout_seconds(3, "alice"), 22)


class ApiPayloadTests(unittest.TestCase):
    @patch("app.time.monotonic")
    @patch("app._upload_pdf_to_paperless", return_value={"id": 4242})
    @patch("app._convert_tiffs_to_pdf", return_value=3)
    @patch("app._run_scan_command", return_value=[Path("/tmp/scan_output1.tiff")])
    def test_process_scan_includes_device_identifiers_in_success_payload(
        self, _mock_run_scan, _mock_convert, _mock_upload, mock_monotonic
    ):
        mock_monotonic.side_effect = [10.0, 11.0, 14.0, 20.0, 22.5, 23.0]
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.get_active_device_name.return_value = "brother-bw"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"

        with patch("app.get_config_manager", return_value=fake_config_manager):
            result = scan_app._process_scan()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["device_name"], "brother-bw")
        self.assertEqual(result["device_id"], "BrotherADS2200:libusb:001:002")
        self.assertEqual(result["scanimage_device_name"], "BrotherADS2200:libusb:001:002")
        self.assertEqual(
            result["timing_metrics"],
            {
                "total_seconds": 13.0,
                "scan_seconds": 3.0,
                "paperless_seconds": 2.5,
                "scan_seconds_per_page": 1.0,
                "paperless_seconds_per_page": 0.833,
            },
        )
        self.assertIn("total=13.0s", result["message"])
        self.assertIn("scan=3.0s", result["message"])
        self.assertIn("paperless=2.5s", result["message"])
        self.assertIn("scan_per_page=1.0s", result["message"])
        self.assertIn("paperless_per_page=0.833s", result["message"])

    @patch("app.time.monotonic")
    @patch("app._upload_pdf_to_paperless", return_value={"id": 4242, "task_id": "task-123"})
    @patch("app._convert_tiffs_to_pdf", return_value=1)
    @patch("app._run_scan_command", return_value=[Path("/tmp/scan_output1.tiff")])
    def test_process_scan_includes_paperless_task_id_from_object_response(
        self, _mock_run_scan, _mock_convert, _mock_upload, mock_monotonic
    ):
        mock_monotonic.side_effect = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.get_active_device_name.return_value = "brother-bw"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"

        with patch("app.get_config_manager", return_value=fake_config_manager):
            result = scan_app._process_scan()

        self.assertEqual(result["paperless_task_id"], "task-123")

    @patch("app.time.monotonic")
    @patch(
        "app._upload_pdf_to_paperless",
        return_value={"raw_response": "cf13eea8-5c7a-40b8-aac8-bd8bdc315769"},
    )
    @patch("app._convert_tiffs_to_pdf", return_value=1)
    @patch("app._run_scan_command", return_value=[Path("/tmp/scan_output1.tiff")])
    def test_process_scan_includes_paperless_task_id_from_raw_uuid_response(
        self, _mock_run_scan, _mock_convert, _mock_upload, mock_monotonic
    ):
        mock_monotonic.side_effect = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.get_active_device_name.return_value = "brother-bw"
        fake_config_manager.get_device_id.return_value = "BrotherADS2200:libusb:001:002"

        with patch("app.get_config_manager", return_value=fake_config_manager):
            result = scan_app._process_scan()

        self.assertEqual(result["paperless_task_id"], "cf13eea8-5c7a-40b8-aac8-bd8bdc315769")


class ApiPaperlessTaskTests(unittest.TestCase):
    def setUp(self):
        scan_app.app.config["TESTING"] = True
        self.client = scan_app.app.test_client()

    @patch("app.requests.get")
    def test_get_paperless_task_status_returns_normalized_started_payload(self, mock_requests_get):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.get_paperless_base_url.return_value = "http://paperless"
        fake_config_manager.get_user_token.return_value = "secret-token"

        task_id = "11e48898-bde8-4695-afd6-5a61452a4b54"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "task_id": task_id,
                "status": "STARTED",
                "related_document": None,
                "result": None,
                "date_done": None,
                "task_file_name": "Offer.pdf",
            }
        ]
        mock_requests_get.return_value = mock_response

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.get(f"/api/paperless/tasks/{task_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["task_id"], task_id)
        self.assertEqual(payload["task_status"], "STARTED")
        self.assertEqual(payload["task_file_name"], "Offer.pdf")
        self.assertIsNone(payload["related_document"])

    @patch("app.requests.get")
    def test_get_paperless_task_status_returns_not_found_when_task_list_empty(self, mock_requests_get):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.get_paperless_base_url.return_value = "http://paperless"
        fake_config_manager.get_user_token.return_value = "secret-token"

        task_id = "cf13eea8-5c7a-40b8-aac8-bd8bdc315769"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_requests_get.return_value = mock_response

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.get(f"/api/paperless/tasks/{task_id}")

        self.assertEqual(response.status_code, 404)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["message"], "Task not found")


class ApiDeviceConfigurationTests(unittest.TestCase):
    def setUp(self):
        scan_app.app.config["TESTING"] = True
        self.client = scan_app.app.test_client()

    def test_get_device_configurations_returns_available_and_selected_device_details(self):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw", "brother-color"]
        fake_config_manager.get_active_device_name.return_value = "brother-bw"
        fake_config_manager.get_user_device.side_effect = [
            {
                "device_id": "scanner-bw",
                "scan_command": "/opt/scanexpress/scripts/scan_wrapper.sh",
                "scan_timeout_seconds": "30",
            },
            {
                "device_id": "scanner-color",
                "scan_command": "/opt/scanexpress/scripts/scan_wrapper.sh",
                "scan_timeout_seconds": "60",
            },
        ]
        fake_config_manager.get_device_scanimage_params.side_effect = [
            {"mode": "Gray", "resolution": "300"},
            {"mode": "Color", "resolution": "200"},
        ]

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.get("/api/device-configurations")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["username"], "alice")
        self.assertEqual(payload["selected_device_name"], "brother-bw")
        self.assertEqual(len(payload["devices"]), 2)
        self.assertEqual(payload["devices"][0]["device_name"], "brother-bw")
        self.assertEqual(payload["devices"][0]["device_id"], "scanner-bw")
        self.assertEqual(payload["devices"][0]["scanimage_params"]["mode"], "Gray")

    @patch("app._upload_pdf_to_paperless", return_value={"id": 4242})
    @patch("app._convert_tiffs_to_pdf", return_value=1)
    @patch("app._run_scan_command", return_value=[Path("/tmp/scan_output1.tiff")])
    def test_post_scan_uses_requested_device_name(self, _mock_run_scan, _mock_convert, _mock_upload):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw", "brother-color"]
        fake_config_manager.get_device_id.return_value = "scanner-color"

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.post("/api/scan", json={"device_name": "brother-color"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["device_name"], "brother-color")

    def test_post_scan_rejects_unknown_requested_device_name(self):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw"]

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.post("/api/scan", json={"device_name": "missing-device"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("not configured", payload["message"])


class ApiScanLockTests(unittest.TestCase):
    def setUp(self):
        scan_app.app.config["TESTING"] = True
        self.client = scan_app.app.test_client()

    def tearDown(self):
        with scan_app._DEVICE_SCAN_LOCK:
            scan_app._ACTIVE_DEVICE_SCANS.clear()

    @patch("app._process_scan")
    def test_post_scan_rejects_when_same_device_is_already_scanning(self, mock_process_scan):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw"]
        fake_config_manager.get_device_id.return_value = "scanner-bw"

        with scan_app._DEVICE_SCAN_LOCK:
            scan_app._ACTIVE_DEVICE_SCANS["scanner-bw"] = {
                "username": "alice",
                "device_name": "brother-bw",
                "started_at": 12345.0,
            }

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.post("/api/scan", json={"device_name": "brother-bw"})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["status"], "busy")
        self.assertIn("already in progress", payload["message"])
        mock_process_scan.assert_not_called()

    def test_get_scan_status_reports_device_in_progress(self):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw"]
        fake_config_manager.get_device_id.return_value = "scanner-bw"

        with scan_app._DEVICE_SCAN_LOCK:
            scan_app._ACTIVE_DEVICE_SCANS["scanner-bw"] = {
                "username": "alice",
                "device_name": "brother-bw",
                "started_at": 12345.0,
            }

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.get("/api/scan/status", query_string={"device_name": "brother-bw"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["in_progress"])
        self.assertEqual(payload["device_lock_id"], "scanner-bw")
        self.assertIn("active_scan", payload)

    @patch("app._process_scan")
    def test_post_scan_stream_rejects_when_same_device_is_already_scanning(self, mock_process_scan):
        fake_config_manager = Mock()
        fake_config_manager.get_current_user.return_value = "alice"
        fake_config_manager.list_user_devices.return_value = ["brother-bw"]
        fake_config_manager.get_device_id.return_value = "scanner-bw"

        with scan_app._DEVICE_SCAN_LOCK:
            scan_app._ACTIVE_DEVICE_SCANS["scanner-bw"] = {
                "username": "alice",
                "device_name": "brother-bw",
                "started_at": 12345.0,
            }

        with patch("app.get_config_manager", return_value=fake_config_manager):
            response = self.client.post("/api/scan/stream", json={"device_name": "brother-bw"})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["status"], "busy")
        self.assertIn("already in progress", payload["message"])
        mock_process_scan.assert_not_called()


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
