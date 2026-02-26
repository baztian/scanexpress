import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from config import ConfigManager


class ConfigManagerTests(unittest.TestCase):
    def _write_config(self, content: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config_path = Path(temp_dir.name) / "config.ini"
        config_path.write_text(dedent(content).strip() + "\n", encoding="utf-8")
        return config_path

    def test_get_user_token_from_user_section(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_user_token("alice"), "token-alice")

    def test_default_config_path_is_etc_scanexpress(self):
        with tempfile.TemporaryDirectory() as temp_home:
            with unittest.mock.patch.dict("os.environ", {"HOME": temp_home}, clear=True):
                manager = ConfigManager()

        self.assertEqual(manager.config_file, Path("/etc/scanexpress.conf"))

    def test_default_config_path_prefers_user_config_before_etc(self):
        with tempfile.TemporaryDirectory() as temp_home:
            user_config_dir = Path(temp_home) / ".config" / "scanexpress"
            user_config_dir.mkdir(parents=True, exist_ok=True)
            user_config_path = user_config_dir / "scanexpress.conf"
            user_config_path.write_text("[global]\ndefault_user = alice\n", encoding="utf-8")

            with unittest.mock.patch.dict("os.environ", {"HOME": temp_home}, clear=True):
                manager = ConfigManager()

        self.assertEqual(manager.config_file, user_config_path)

    def test_env_config_path_override_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override_path = Path(temp_dir) / "custom.conf"
            override_path.write_text("[global]\ndefault_user = alice\n", encoding="utf-8")

            with unittest.mock.patch.dict(
                "os.environ", {"SCANEXPRESS_CONFIG_FILE": str(override_path)}, clear=True
            ):
                manager = ConfigManager()

        self.assertEqual(manager.config_file, override_path)

    def test_get_user_token_requires_user_token_in_config(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_user_token("alice")

        self.assertIn("No paperless API token configured", str(context.exception))

    def test_get_filename_template_returns_configured_template(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice
            filename_template = inbox_{base62_id}

            [user:alice]
            paperless_api_token = token-alice
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_filename_template(), "inbox_{base62_id}")

    def test_get_filename_template_returns_none_when_missing(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            """
        )

        manager = ConfigManager(config_path)

        self.assertIsNone(manager.get_filename_template())

    def test_list_user_devices_returns_only_matching_user_devices(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-color]
            device_id = scanner-1

            [user:alice:device:brother-bw]
            device_id = scanner-1

            [user:bob]
            paperless_api_token = token-bob

            [user:bob:device:canon-default]
            device_id = scanner-2
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.list_user_devices("alice"), ["brother-bw", "brother-color"])

    def test_list_user_devices_ignores_scanimage_params_subsections(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-color]
            device_id = scanner-1

            [user:alice:device:brother-color:scanimage-params]
            mode = Color
            resolution = 300
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.list_user_devices("alice"), ["brother-color"])

    def test_list_user_devices_includes_global_devices(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-bw]
            device_id = scanner-1

            [device:shared-flatbed]
            device_id = scanner-2
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(
            manager.list_user_devices("alice"),
            ["brother-bw", "shared-flatbed"],
        )

    def test_get_user_device_falls_back_to_global_device(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [device:shared-flatbed]
            device_id = scanner-2
            scan_output_mode = single_file
            """
        )

        manager = ConfigManager(config_path)
        device = manager.get_user_device("alice", "shared-flatbed")

        self.assertEqual(device["device_id"], "scanner-2")
        self.assertEqual(device["scan_output_mode"], "single_file")

    def test_get_user_device_prefers_user_specific_device_over_global(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [device:shared-flatbed]
            device_id = global-scanner
            scan_output_mode = single_file

            [user:alice:device:shared-flatbed]
            device_id = alice-scanner
            scan_output_mode = batch
            """
        )

        manager = ConfigManager(config_path)
        device = manager.get_user_device("alice", "shared-flatbed")

        self.assertEqual(device["device_id"], "alice-scanner")
        self.assertEqual(device["scan_output_mode"], "batch")

    def test_get_active_device_accepts_global_default_device(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = shared-flatbed

            [device:shared-flatbed]
            device_id = scanner-2
            scan_output_mode = single_file
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_active_device_name("alice"), "shared-flatbed")

    def test_get_device_scanimage_params_falls_back_to_global_device_section(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = shared-flatbed

            [device:shared-flatbed]
            device_id = scanner-2
            scan_output_mode = single_file
            resolution = 300
            mode = Gray
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(
            manager.get_device_scanimage_params("alice"),
            {
                "resolution": "300",
                "mode": "Gray",
            },
        )

    def test_get_device_id_prefers_user_specific_device_over_global(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = shared-flatbed

            [device:shared-flatbed]
            device_id = global-scanner
            scan_output_mode = single_file

            [user:alice:device:shared-flatbed]
            device_id = alice-scanner
            scan_output_mode = batch
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_device_id("alice", "shared-flatbed"), "alice-scanner")

    def test_get_user_device_returns_settings_dict(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-color]
            device_id = scanner-1
            scan_command = /opt/scanexpress/scripts/scan_wrapper.sh
            scan_timeout_seconds = 30
            resolution = 300
            mode = 24 bit Color
            """
        )

        manager = ConfigManager(config_path)
        device = manager.get_user_device("alice", "brother-color")

        self.assertEqual(device["device_id"], "scanner-1")
        self.assertEqual(device["scan_command"], "/opt/scanexpress/scripts/scan_wrapper.sh")
        self.assertEqual(device["scan_timeout_seconds"], "30")
        self.assertEqual(device["resolution"], "300")

    def test_get_current_user_reads_global_default_user(self):
        config_path = self._write_config(
            """
            [global]
            default_user = bob

            [user:alice]
            paperless_api_token = token-alice
            [user:bob]
            paperless_api_token = token-bob
            """
        )

        manager = ConfigManager(config_path)
        self.assertEqual(manager.get_current_user(), "bob")

    def test_get_current_user_requires_global_default_user(self):
        config_path = self._write_config(
            """
            [user:alice]
            paperless_api_token = token-alice

            [user:bob]
            paperless_api_token = token-bob
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_current_user()

        self.assertIn("global.default_user", str(context.exception))

    def test_get_current_user_must_exist_in_configured_users(self):
        config_path = self._write_config(
            """
            [global]
            default_user = charlie

            [user:alice]
            paperless_api_token = token-alice

            [user:bob]
            paperless_api_token = token-bob
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_current_user()

        self.assertIn("user 'charlie' not found", str(context.exception))

    def test_get_active_device_requires_default_device_when_devices_exist(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-color]
            device_id = scanner-1

            [user:alice:device:brother-bw]
            device_id = scanner-1
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_active_device_name("alice")

        self.assertIn("default_device is required", str(context.exception))

    def test_get_active_device_uses_user_default_device_when_configured(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = brother-color

            [user:alice:device:brother-color]
            device_id = scanner-1

            [user:alice:device:brother-bw]
            device_id = scanner-1
            """
        )

        manager = ConfigManager(config_path)
        self.assertEqual(manager.get_active_device_name("alice"), "brother-color")

    def test_get_active_device_returns_none_when_no_devices_are_configured(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            """
        )

        manager = ConfigManager(config_path)
        self.assertIsNone(manager.get_active_device_name("alice"))

    def test_get_active_device_raises_for_invalid_default_device(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = missing-device

            [user:alice:device:brother-color]
            device_id = scanner-1
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_active_device_name("alice")

        self.assertIn("default_device", str(context.exception))
        self.assertIn("missing-device", str(context.exception))

    def test_get_device_scanimage_params_uses_dedicated_section_when_present(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-bw]
            device_id = scanner-1
            scan_timeout_seconds = 30
            resolution = 200

            [user:alice:device:brother-bw:scanimage-params]
            resolution = 300
            mode = Gray
            source = Automatic Document Feeder
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(
            manager.get_device_scanimage_params("alice", "brother-bw"),
            {
                "mode": "Gray",
                "resolution": "300",
                "source": "Automatic Document Feeder",
            },
        )

    def test_get_device_scanimage_params_falls_back_to_device_section(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice

            [user:alice:device:brother-color]
            device_id = scanner-1
            scan_command = /usr/bin/scanimage
            scan_timeout_seconds = 30
            resolution = 300
            mode = 24 bit Color
            source = Automatic Document Feeder
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(
            manager.get_device_scanimage_params("alice", "brother-color"),
            {
                "mode": "24 bit Color",
                "resolution": "300",
                "source": "Automatic Document Feeder",
            },
        )

    def test_get_device_scanimage_params_uses_user_default_scanimage_params_device(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = brother-color
            default_scanimage_params_device = brother-bw

            [user:alice:device:brother-color]
            device_id = scanner-1

            [user:alice:device:brother-color:scanimage-params]
            resolution = 300
            mode = 24 bit Color

            [user:alice:device:brother-bw]
            device_id = scanner-1

            [user:alice:device:brother-bw:scanimage-params]
            resolution = 200
            mode = Gray
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(
            manager.get_device_scanimage_params("alice"),
            {
                "mode": "Gray",
                "resolution": "200",
            },
        )

    def test_get_device_scanimage_params_raises_for_invalid_default_scanimage_params_device(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_scanimage_params_device = missing-profile

            [user:alice:device:brother-color]
            device_id = scanner-1
            """
        )

        manager = ConfigManager(config_path)
        with self.assertRaises(RuntimeError) as context:
            manager.get_device_scanimage_params("alice")

        self.assertIn("default_scanimage_params_device", str(context.exception))
        self.assertIn("missing-profile", str(context.exception))

    def test_get_paperless_base_url_reads_global_config(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice
            paperless_base_url = https://paperless.example.com

            [user:alice]
            paperless_api_token = token-alice
            """
        )

        manager = ConfigManager(config_path)
        self.assertEqual(manager.get_paperless_base_url(), "https://paperless.example.com")

    def test_get_device_scan_output_mode_reads_explicit_batch_mode(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = brother-color

            [user:alice:device:brother-color]
            device_id = scanner-1
            scan_output_mode = batch
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_device_scan_output_mode("alice", "brother-color"), "batch")

    def test_get_device_scan_output_mode_reads_explicit_single_file_mode(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = flatbed

            [user:alice:device:flatbed]
            device_id = scanner-1
            scan_output_mode = single_file
            """
        )

        manager = ConfigManager(config_path)

        self.assertEqual(manager.get_device_scan_output_mode("alice", "flatbed"), "single_file")

    def test_get_device_scan_output_mode_requires_explicit_value(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = flatbed

            [user:alice:device:flatbed]
            device_id = scanner-1
            """
        )

        manager = ConfigManager(config_path)

        with self.assertRaises(RuntimeError) as context:
            manager.get_device_scan_output_mode("alice", "flatbed")

        self.assertIn("scan_output_mode", str(context.exception))

    def test_get_device_scan_output_mode_rejects_invalid_value(self):
        config_path = self._write_config(
            """
            [global]
            default_user = alice

            [user:alice]
            paperless_api_token = token-alice
            default_device = flatbed

            [user:alice:device:flatbed]
            device_id = scanner-1
            scan_output_mode = invalid-mode
            """
        )

        manager = ConfigManager(config_path)

        with self.assertRaises(RuntimeError) as context:
            manager.get_device_scan_output_mode("alice", "flatbed")

        self.assertIn("scan_output_mode", str(context.exception))
        self.assertIn("invalid-mode", str(context.exception))


if __name__ == "__main__":
    unittest.main()
