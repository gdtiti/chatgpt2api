import json
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
ROOT_CONFIG_FILE = ROOT_DIR / "config.json"


class ConfigLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._created_root_config = False
        if not ROOT_CONFIG_FILE.exists():
            ROOT_CONFIG_FILE.write_text(json.dumps({"auth-key": "test-auth"}), encoding="utf-8")
            cls._created_root_config = True

        from services import config as config_module

        cls.config_module = config_module

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._created_root_config and ROOT_CONFIG_FILE.exists():
            ROOT_CONFIG_FILE.unlink()

    def test_load_settings_ignores_directory_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            data_dir = base_dir / "data"
            config_dir = base_dir / "config.json"
            os_auth_key = "env-auth"

            config_dir.mkdir()

            module = self.config_module
            old_base_dir = module.BASE_DIR
            old_data_dir = module.DATA_DIR
            old_config_file = module.CONFIG_FILE
            old_env_auth_key = module.os.environ.get("CHATGPT2API_AUTH_KEY")
            try:
                module.BASE_DIR = base_dir
                module.DATA_DIR = data_dir
                module.CONFIG_FILE = config_dir
                module.os.environ["CHATGPT2API_AUTH_KEY"] = os_auth_key

                settings = module._load_settings()

                self.assertEqual(settings.auth_key, os_auth_key)
                self.assertEqual(settings.refresh_account_interval_minute, 5)
                self.assertEqual(settings.port, 80)
            finally:
                module.BASE_DIR = old_base_dir
                module.DATA_DIR = old_data_dir
                module.CONFIG_FILE = old_config_file
                if old_env_auth_key is None:
                    module.os.environ.pop("CHATGPT2API_AUTH_KEY", None)
                else:
                    module.os.environ["CHATGPT2API_AUTH_KEY"] = old_env_auth_key

    def test_default_config_file_is_under_data_dir(self) -> None:
        module = self.config_module

        self.assertEqual(module.CONFIG_FILE, module.DATA_DIR / "config.json")

    def test_startup_paths_support_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            data_dir = base_dir / "runtime-data"
            config_file = base_dir / "custom-config.json"

            module = self.config_module
            old_base_dir = module.BASE_DIR
            old_data_dir_env = module.os.environ.get("CHATGPT2API_DATA_DIR")
            old_config_file_env = module.os.environ.get("CHATGPT2API_CONFIG_FILE")
            try:
                module.BASE_DIR = base_dir
                module.os.environ["CHATGPT2API_DATA_DIR"] = str(data_dir)
                module.os.environ["CHATGPT2API_CONFIG_FILE"] = str(config_file)

                self.assertEqual(module._resolve_startup_path("CHATGPT2API_DATA_DIR", base_dir / "data"), data_dir)
                self.assertEqual(
                    module._resolve_startup_path("CHATGPT2API_CONFIG_FILE", data_dir / "config.json"),
                    config_file,
                )

                module.os.environ["CHATGPT2API_CONFIG_FILE"] = "relative-config.json"
                self.assertEqual(
                    module._resolve_startup_path("CHATGPT2API_CONFIG_FILE", data_dir / "config.json"),
                    base_dir / "relative-config.json",
                )
            finally:
                module.BASE_DIR = old_base_dir
                if old_data_dir_env is None:
                    module.os.environ.pop("CHATGPT2API_DATA_DIR", None)
                else:
                    module.os.environ["CHATGPT2API_DATA_DIR"] = old_data_dir_env
                if old_config_file_env is None:
                    module.os.environ.pop("CHATGPT2API_CONFIG_FILE", None)
                else:
                    module.os.environ["CHATGPT2API_CONFIG_FILE"] = old_config_file_env

    def test_config_store_migrates_legacy_config_to_data_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            data_dir = base_dir / "data"
            new_config_file = data_dir / "config.json"
            legacy_config_file = base_dir / "config.json"
            legacy_config_file.write_text(
                json.dumps({"auth-key": "legacy-auth", "refresh_account_interval_minute": 12}),
                encoding="utf-8",
            )

            module = self.config_module
            old_data_dir = module.DATA_DIR
            old_config_file = module.CONFIG_FILE
            old_legacy_config_file = module.LEGACY_CONFIG_FILE
            try:
                module.DATA_DIR = data_dir
                module.CONFIG_FILE = new_config_file
                module.LEGACY_CONFIG_FILE = legacy_config_file

                store = module.ConfigStore(new_config_file)

                self.assertEqual(store.auth_key, "legacy-auth")
                self.assertTrue(new_config_file.exists())
                self.assertTrue(legacy_config_file.exists())
                self.assertEqual(json.loads(new_config_file.read_text(encoding="utf-8"))["auth-key"], "legacy-auth")
            finally:
                module.DATA_DIR = old_data_dir
                module.CONFIG_FILE = old_config_file
                module.LEGACY_CONFIG_FILE = old_legacy_config_file

    def test_config_store_prefers_non_empty_env_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "auth-key": "file-auth",
                        "port": 8080,
                        "refresh_account_interval_minute": 60,
                        "proxy": "http://file-proxy:8080",
                        "base_url": "https://file.example.com/",
                        "image_url_prefix": "https://file-images.example.com/resolve/",
                        "image_url_template": "https://file-images.example.com/{date}/{file}",
                    }
                ),
                encoding="utf-8",
            )

            module = self.config_module
            env_names = {
                "CHATGPT2API_AUTH_KEY": "env-auth",
                "CHATGPT2API_PORT": "9090",
                "CHATGPT2API_REFRESH_ACCOUNT_INTERVAL_MINUTE": "15",
                "CHATGPT2API_PROXY": "http://env-proxy:9090",
                "CHATGPT2API_BASE_URL": "https://env.example.com/",
                "CHATGPT2API_IMAGE_URL_PREFIX": "https://env-images.example.com/resolve/",
                "CHATGPT2API_IMAGE_URL_TEMPLATE": "https://env-images.example.com/{path}",
            }
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name, value in env_names.items():
                    module.os.environ[name] = value

                store = module.ConfigStore(config_file)

                self.assertEqual(store.auth_key, "env-auth")
                self.assertEqual(store.listen_port, 9090)
                self.assertEqual(store.refresh_account_interval_minute, 15)
                self.assertEqual(store.get_proxy_settings(), "http://env-proxy:9090")
                self.assertEqual(store.base_url, "https://env.example.com")
                self.assertEqual(store.image_url_prefix, "https://env-images.example.com/resolve")
                self.assertEqual(store.image_url_template, "https://env-images.example.com/{path}")
                self.assertEqual(store.get_effective()["image_url_prefix"], "https://env-images.example.com/resolve")
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value

    def test_config_store_falls_back_to_file_when_env_is_blank_or_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "auth-key": "file-auth",
                        "port": 8080,
                        "refresh_account_interval_minute": 60,
                        "proxy": "http://file-proxy:8080",
                        "base_url": "https://file.example.com/",
                        "image_url_prefix": "https://file-images.example.com/resolve/",
                        "image_url_template": "https://file-images.example.com/{date}/{file}",
                    }
                ),
                encoding="utf-8",
            )

            module = self.config_module
            env_names = {
                "CHATGPT2API_AUTH_KEY": "   ",
                "CHATGPT2API_PORT": "70000",
                "PORT": "7070",
                "CHATGPT2API_REFRESH_ACCOUNT_INTERVAL_MINUTE": "invalid",
                "CHATGPT2API_PROXY": " ",
                "CHATGPT2API_BASE_URL": "",
                "CHATGPT2API_IMAGE_URL_PREFIX": "",
                "CHATGPT2API_IMAGE_URL_TEMPLATE": " ",
            }
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name, value in env_names.items():
                    module.os.environ[name] = value

                store = module.ConfigStore(config_file)

                self.assertEqual(store.auth_key, "file-auth")
                self.assertEqual(store.listen_port, 7070)
                self.assertEqual(store.refresh_account_interval_minute, 60)
                self.assertEqual(store.get_proxy_settings(), "http://file-proxy:8080")
                self.assertEqual(store.base_url, "https://file.example.com")
                self.assertEqual(store.image_url_prefix, "https://file-images.example.com/resolve")
                self.assertEqual(store.image_url_template, "https://file-images.example.com/{date}/{file}")
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value

    def test_config_store_falls_back_to_file_port_when_env_port_is_missing_or_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "auth-key": "file-auth",
                        "port": 8080,
                    }
                ),
                encoding="utf-8",
            )

            module = self.config_module
            env_names = {
                "CHATGPT2API_PORT": "0",
                "PORT": "invalid",
            }
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name, value in env_names.items():
                    module.os.environ[name] = value

                store = module.ConfigStore(config_file)

                self.assertEqual(store.listen_port, 8080)
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value

    def test_config_store_supports_image_strategy_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            placeholder_path = Path(tmp_dir) / "placeholder.png"
            placeholder_path.write_bytes(b"placeholder-image")
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "auth-key": "file-auth",
                        "image_failure_strategy": "placeholder",
                        "image_retry_count": 2,
                        "image_parallel_attempts": 3,
                        "image_placeholder_path": str(placeholder_path),
                    }
                ),
                encoding="utf-8",
            )

            module = self.config_module
            env_names = {
                "CHATGPT2API_IMAGE_FAILURE_STRATEGY": "retry",
                "CHATGPT2API_IMAGE_RETRY_COUNT": "1",
                "CHATGPT2API_IMAGE_PARALLEL_ATTEMPTS": "4",
                "CHATGPT2API_IMAGE_PLACEHOLDER_PATH": "",
            }
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name, value in env_names.items():
                    module.os.environ[name] = value

                store = module.ConfigStore(config_file)

                self.assertEqual(store.image_failure_strategy, "retry")
                self.assertEqual(store.image_retry_count, 1)
                self.assertEqual(store.image_parallel_attempts, 4)
                self.assertEqual(store.get_effective()["image_failure_strategy"], "retry")
                self.assertEqual(store.env_overrides()["image_failure_strategy"], "CHATGPT2API_IMAGE_FAILURE_STRATEGY")
                self.assertEqual(store.image_placeholder_path, placeholder_path)
                self.assertEqual(store.api_keys_file.name, "api_keys.json")
                self.assertEqual(store.jobs_dir.name, "jobs")
                self.assertEqual(store.job_results_dir.name, "job_results")
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value

    def test_config_store_supports_image_storage_and_cleanup_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(
                json.dumps(
                    {
                        "auth-key": "file-auth",
                        "image_response_format": "b64_json",
                        "image_url_include_b64_when_requested": False,
                        "image_thumbnail_max_size": 512,
                        "image_thumbnail_quality": 85,
                        "image_wall_thumbnail_max_size": 960,
                        "openai_compat_image_task_tracking_enabled": False,
                        "openai_compat_image_gallery_enabled": False,
                        "openai_compat_image_waterfall_enabled": False,
                        "image_retention_days": 7,
                        "task_log_retention_days": 9,
                        "system_log_max_mb": 32,
                        "data_cleanup_enabled": False,
                        "data_cleanup_interval_minutes": 120,
                    }
                ),
                encoding="utf-8",
            )

            module = self.config_module
            env_names = {
                "CHATGPT2API_IMAGE_RESPONSE_FORMAT": "url",
                "CHATGPT2API_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED": "true",
                "CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE": "320",
                "CHATGPT2API_IMAGE_THUMBNAIL_QUALITY": "72",
                "CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE": "1280",
                "CHATGPT2API_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED": "true",
                "CHATGPT2API_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED": "true",
                "CHATGPT2API_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED": "true",
                "CHATGPT2API_IMAGE_RETENTION_DAYS": "3",
                "CHATGPT2API_TASK_LOG_RETENTION_DAYS": "5",
                "CHATGPT2API_SYSTEM_LOG_MAX_MB": "64",
                "CHATGPT2API_DATA_CLEANUP_ENABLED": "true",
                "CHATGPT2API_DATA_CLEANUP_INTERVAL_MINUTES": "45",
            }
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name, value in env_names.items():
                    module.os.environ[name] = value

                store = module.ConfigStore(config_file)

                self.assertEqual(store.image_response_format, "url")
                self.assertEqual(store.image_url_include_b64_when_requested, True)
                self.assertEqual(store.image_thumbnail_max_size, 320)
                self.assertEqual(store.image_thumbnail_quality, 72)
                self.assertEqual(store.image_wall_thumbnail_max_size, 1280)
                self.assertEqual(store.openai_compat_image_task_tracking_enabled, True)
                self.assertEqual(store.openai_compat_image_gallery_enabled, True)
                self.assertEqual(store.openai_compat_image_waterfall_enabled, True)
                self.assertEqual(
                    store.env_overrides()["openai_compat_image_task_tracking_enabled"],
                    "CHATGPT2API_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED",
                )
                self.assertEqual(store.image_retention_days, 3)
                self.assertEqual(store.task_log_retention_days, 5)
                self.assertEqual(store.system_log_max_mb, 64)
                self.assertEqual(store.data_cleanup_enabled, True)
                self.assertEqual(store.data_cleanup_interval_minutes, 45)
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value

    def test_config_store_update_persists_image_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_file.write_text(json.dumps({"auth-key": "file-auth"}), encoding="utf-8")

            module = self.config_module
            env_names = [
                "CHATGPT2API_IMAGE_FAILURE_STRATEGY",
                "CHATGPT2API_IMAGE_RETRY_COUNT",
                "CHATGPT2API_IMAGE_PARALLEL_ATTEMPTS",
                "CHATGPT2API_IMAGE_PLACEHOLDER_PATH",
            ]
            old_env = {name: module.os.environ.get(name) for name in env_names}
            try:
                for name in env_names:
                    module.os.environ.pop(name, None)

                store = module.ConfigStore(config_file)
                store.update(
                    {
                        "image_failure_strategy": "placeholder",
                        "image_retry_count": 2,
                        "image_parallel_attempts": 3,
                        "image_placeholder_path": "data/placeholders/fallback.png",
                    }
                )

                reloaded_store = module.ConfigStore(config_file)
                reloaded_data = json.loads(config_file.read_text(encoding="utf-8"))

                self.assertEqual(reloaded_store.image_failure_strategy, "placeholder")
                self.assertEqual(reloaded_store.image_retry_count, 2)
                self.assertEqual(reloaded_store.image_parallel_attempts, 3)
                self.assertEqual(reloaded_data["image_placeholder_path"], "data/placeholders/fallback.png")
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
