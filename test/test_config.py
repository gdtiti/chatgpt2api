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
                self.assertEqual(store.refresh_account_interval_minute, 60)
                self.assertEqual(store.get_proxy_settings(), "http://file-proxy:8080")
                self.assertEqual(store.base_url, "https://file.example.com")
            finally:
                for name, value in old_env.items():
                    if value is None:
                        module.os.environ.pop(name, None)
                    else:
                        module.os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
