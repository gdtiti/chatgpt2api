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


if __name__ == "__main__":
    unittest.main()
