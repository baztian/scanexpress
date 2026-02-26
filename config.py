import os
from configparser import ConfigParser
from pathlib import Path

from werkzeug.security import check_password_hash


class ConfigManager:
    """Manages reading and accessing ScanExpress configuration."""

    def __init__(self, config_file: Path | None = None):
        configured_path = config_file
        if configured_path is None:
            env_config_path = os.getenv("SCANEXPRESS_CONFIG_FILE", "").strip()
            if env_config_path:
                configured_path = Path(env_config_path)
            else:
                configured_path = self._resolve_default_config_path()

        self._config_file = configured_path
        self._parser = ConfigParser()
        self.reload()

    def _resolve_default_config_path(self) -> Path:
        user_config_path = Path("~/.config/scanexpress/scanexpress.conf").expanduser()
        system_config_path = Path("/etc/scanexpress.conf")

        for candidate in (user_config_path, system_config_path):
            if candidate.exists():
                return candidate

        return system_config_path

    @property
    def config_file(self) -> Path:
        return self._config_file

    def reload(self) -> None:
        self._parser = ConfigParser()
        self._parser.read(self._config_file, encoding="utf-8")

    def _section_name_user(self, username: str) -> str:
        return f"user:{username}"

    def _section_name_device(self, username: str, device_name: str) -> str:
        return f"user:{username}:device:{device_name}"

    def _section_name_global_device(self, device_name: str) -> str:
        return f"device:{device_name}"

    def _section_name_device_scanimage_params(self, username: str, device_name: str) -> str:
        return f"{self._section_name_device(username, device_name)}:scanimage-params"

    def _section_name_global_device_scanimage_params(self, device_name: str) -> str:
        return f"{self._section_name_global_device(device_name)}:scanimage-params"

    def _resolve_device_section_name(self, username: str, device_name: str) -> str | None:
        user_device_section_name = self._section_name_device(username, device_name)
        if self._parser.has_section(user_device_section_name):
            return user_device_section_name

        global_device_section_name = self._section_name_global_device(device_name)
        if self._parser.has_section(global_device_section_name):
            return global_device_section_name

        return None

    def _resolve_device_scanimage_params_section_name(
        self, username: str, device_name: str
    ) -> str | None:
        user_params_section_name = self._section_name_device_scanimage_params(
            username, device_name
        )
        if self._parser.has_section(user_params_section_name):
            return user_params_section_name

        global_params_section_name = self._section_name_global_device_scanimage_params(
            device_name
        )
        if self._parser.has_section(global_params_section_name):
            return global_params_section_name

        return None

    def _read_device_key(self, username: str, device_name: str, key: str) -> str | None:
        device_section_name = self._resolve_device_section_name(username, device_name)
        if device_section_name is None:
            return None

        return self._read_section_key(device_section_name, key)

    def _strip_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped == "":
            return None
        return stripped

    def _read_section_key(self, section_name: str, key: str) -> str | None:
        if not self._parser.has_section(section_name):
            return None
        if not self._parser.has_option(section_name, key):
            return None
        return self._strip_value(self._parser.get(section_name, key))

    def _parse_positive_int(self, raw_value: str, source_name: str) -> int:
        try:
            parsed_value = int(raw_value)
        except ValueError as exc:
            raise RuntimeError(f"{source_name} must be an integer.") from exc

        if parsed_value <= 0:
            raise RuntimeError(f"{source_name} must be greater than zero.")

        return parsed_value

    def list_users(self) -> list[str]:
        users = set()
        for section_name in self._parser.sections():
            if not section_name.startswith("user:"):
                continue
            if ":device:" in section_name:
                continue
            users.add(section_name[len("user:") :])
        return sorted(users)

    def user_exists(self, username: str) -> bool:
        return self._parser.has_section(self._section_name_user(username))

    def get_current_user(self) -> str:
        configured_user = self._read_section_key("global", "default_user")
        if configured_user is None:
            raise RuntimeError("global.default_user is not configured.")

        if self.user_exists(configured_user):
            return configured_user

        configured_users = self.list_users()
        available_users = ", ".join(configured_users) if configured_users else "none"
        raise RuntimeError(
            f"global.default_user={configured_user} but user '{configured_user}' "
            f"not found in {self._config_file.name}. Available users: {available_users}"
        )

    def get_default_user(self) -> str | None:
        configured_user = self._read_section_key("global", "default_user")
        if configured_user is None:
            return None

        if self.user_exists(configured_user):
            return configured_user

        configured_users = self.list_users()
        available_users = ", ".join(configured_users) if configured_users else "none"
        raise RuntimeError(
            f"global.default_user={configured_user} but user '{configured_user}' "
            f"not found in {self._config_file.name}. Available users: {available_users}"
        )

    def get_global(self, key: str) -> str | None:
        return self._read_section_key("global", key)

    def get_user_token(self, username: str) -> str:
        token = self._read_section_key(self._section_name_user(username), "paperless_api_token")
        if token is not None:
            return token

        raise RuntimeError(
            f"No paperless API token configured for user '{username}' in config.ini."
        )

    def get_user_password_hash(self, username: str) -> str:
        password_hash = self._read_section_key(self._section_name_user(username), "password_hash")
        if password_hash is not None:
            return password_hash

        raise RuntimeError(
            f"No password_hash configured for user '{username}' in config.ini."
        )

    def verify_user_password(self, username: str, plain_password: str) -> bool:
        if not isinstance(username, str) or username.strip() == "":
            return False
        if not isinstance(plain_password, str) or plain_password == "":
            return False
        if not self.user_exists(username):
            return False

        try:
            password_hash = self.get_user_password_hash(username)
        except RuntimeError:
            return False

        return check_password_hash(password_hash, plain_password)

    def get_user_scan_command(self, username: str, device_name: str | None = None) -> str | None:
        selected_device_name = device_name or self.get_active_device_name(username)
        if selected_device_name is not None:
            command = self._read_device_key(username, selected_device_name, "scan_command")
            if command is not None:
                return command

        command = self._read_section_key(self._section_name_user(username), "scan_command")
        if command is not None:
            return command

        return None

    def list_user_devices(self, username: str) -> list[str]:
        user_prefix = f"{self._section_name_user(username)}:device:"
        global_prefix = "device:"
        devices = set()
        for section_name in self._parser.sections():
            device_name = None
            if section_name.startswith(user_prefix):
                device_name = section_name[len(user_prefix) :]
            elif section_name.startswith(global_prefix):
                device_name = section_name[len(global_prefix) :]

            if device_name is not None:
                if ":" in device_name:
                    continue
                devices.add(device_name)

        return sorted(devices)

    def get_active_device_name(self, username: str) -> str | None:
        configured_devices = self.list_user_devices(username)
        if not configured_devices:
            return None

        default_device = self._read_section_key(
            self._section_name_user(username), "default_device"
        )
        if default_device is None:
            configured_devices_str = ", ".join(configured_devices)
            raise RuntimeError(
                f"{self._section_name_user(username)}.default_device is required when "
                f"devices are configured for user '{username}'. Available devices: "
                f"{configured_devices_str}"
            )

        if default_device in configured_devices:
            return default_device

        configured_devices_str = ", ".join(configured_devices)
        raise RuntimeError(
            f"{self._section_name_user(username)}.default_device={default_device} "
            f"but device '{default_device}' is not configured for user '{username}'. "
            f"Available devices: {configured_devices_str}"
        )

    def get_active_scanimage_params_device_name(
        self, username: str, device_name: str | None = None
    ) -> str | None:
        if device_name is not None:
            return device_name

        configured_devices = self.list_user_devices(username)
        if not configured_devices:
            return None

        default_scanimage_params_device = self._read_section_key(
            self._section_name_user(username), "default_scanimage_params_device"
        )
        if default_scanimage_params_device is not None:
            if default_scanimage_params_device in configured_devices:
                return default_scanimage_params_device
            configured_devices_str = ", ".join(configured_devices)
            raise RuntimeError(
                f"{self._section_name_user(username)}.default_scanimage_params_device="
                f"{default_scanimage_params_device} but device "
                f"'{default_scanimage_params_device}' is not configured for user '{username}'. "
                f"Available devices: {configured_devices_str}"
            )

        return self.get_active_device_name(username)

    def get_user_device(self, username: str, device_name: str) -> dict:
        section_name = self._resolve_device_section_name(username, device_name)
        if section_name is None:
            raise RuntimeError(
                f"Device '{device_name}' is not configured for user '{username}'."
            )

        return dict(self._parser.items(section_name))

    def get_device_scanimage_params(
        self, username: str, device_name: str | None = None
    ) -> dict[str, str]:
        selected_device_name = self.get_active_scanimage_params_device_name(username, device_name)
        if selected_device_name is None:
            return {}

        dedicated_section_name = self._resolve_device_scanimage_params_section_name(
            username, selected_device_name
        )
        if dedicated_section_name is not None:
            params = {}
            for key, value in self._parser.items(dedicated_section_name):
                params[key] = value.strip()
            return params

        device_section_name = self._resolve_device_section_name(username, selected_device_name)
        if device_section_name is None:
            return {}

        reserved_device_keys = {
            "device_id",
            "scan_command",
            "scan_output_mode",
            "scan_timeout_seconds",
        }
        params = {}
        for key, value in self._parser.items(device_section_name):
            if key in reserved_device_keys:
                continue
            params[key] = value.strip()

        return params

    def get_device_id(self, username: str, device_name: str | None = None) -> str | None:
        selected_device_name = device_name or self.get_active_device_name(username)
        if selected_device_name is not None:
            device_id = self._read_device_key(username, selected_device_name, "device_id")
            if device_id is not None:
                return device_id

        return None

    def get_device_scan_output_mode(
        self, username: str, device_name: str | None = None
    ) -> str:
        selected_device_name = device_name or self.get_active_device_name(username)
        if selected_device_name is None:
            raise RuntimeError(
                f"No device configured for user '{username}', cannot resolve scan_output_mode."
            )

        section_name = self._resolve_device_section_name(username, selected_device_name)
        if section_name is None:
            raise RuntimeError(
                f"Device '{selected_device_name}' is not configured for user '{username}'."
            )

        configured_mode = self._read_section_key(section_name, "scan_output_mode")
        if configured_mode is None:
            raise RuntimeError(
                f"{section_name}.scan_output_mode is required and must be set to "
                "'batch' or 'single_file'."
            )

        normalized_mode = configured_mode.strip().lower()
        if normalized_mode not in {"batch", "single_file"}:
            raise RuntimeError(
                f"{section_name}.scan_output_mode={configured_mode} is invalid. "
                "Use 'batch' or 'single_file'."
            )

        return normalized_mode

    def get_device_scan_timeout_seconds(
        self, username: str, device_name: str | None = None
    ) -> int | None:
        selected_device_name = device_name or self.get_active_device_name(username)
        if selected_device_name is not None:
            section_name = self._resolve_device_section_name(username, selected_device_name)
            device_timeout = None
            if section_name is not None:
                device_timeout = self._read_section_key(
                    section_name,
                    "scan_timeout_seconds",
                )
            if device_timeout is not None:
                return self._parse_positive_int(
                    device_timeout,
                    f"{section_name}.scan_timeout_seconds",
                )

        global_timeout = self.get_global("scan_timeout_seconds")
        if global_timeout is not None:
            return self._parse_positive_int(global_timeout, "scan_timeout_seconds")

        return None

    def get_paperless_base_url(self) -> str:
        base_url = self.get_global("paperless_base_url")
        if base_url is None:
            raise RuntimeError("global.paperless_base_url is not configured.")
        return base_url

    def get_filename_template(self) -> str | None:
        return self.get_global("filename_template")

    def get_paperless_timeout_seconds(self) -> int | None:
        timeout_value = self.get_global("paperless_timeout_seconds")
        if timeout_value is None:
            return None

        return self._parse_positive_int(timeout_value, "paperless_timeout_seconds")
