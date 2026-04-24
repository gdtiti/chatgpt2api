from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
VERSION_FILE = BASE_DIR / "VERSION"
DEFAULT_REFRESH_ACCOUNT_INTERVAL_MINUTE = 5
ENV_AUTH_KEY = "CHATGPT2API_AUTH_KEY"
ENV_REFRESH_ACCOUNT_INTERVAL_MINUTE = "CHATGPT2API_REFRESH_ACCOUNT_INTERVAL_MINUTE"
ENV_PROXY = "CHATGPT2API_PROXY"
ENV_BASE_URL = "CHATGPT2API_BASE_URL"


@dataclass(frozen=True)
class LoadedSettings:
    auth_key: str
    refresh_account_interval_minute: int


def _normalize_auth_key(value: object) -> str:
    return str(value or "").strip()


def _is_invalid_auth_key(value: object) -> bool:
    return _normalize_auth_key(value) == ""


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _read_env_text(name: str) -> str:
    return _normalize_text(os.getenv(name))


def _resolve_text_setting(raw_config: dict[str, object], key: str, env_name: str) -> str:
    env_value = _read_env_text(env_name)
    if env_value:
        return env_value
    return _normalize_text(raw_config.get(key))


def _parse_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_int_setting(raw_config: dict[str, object], key: str, env_name: str, default: int) -> int:
    env_value = _parse_int(os.getenv(env_name))
    if env_value is not None:
        return env_value
    file_value = _parse_int(raw_config.get(key))
    if file_value is not None:
        return file_value
    return default


def _read_json_object(path: Path, *, name: str) -> dict[str, object]:
    if not path.exists():
        return {}
    if path.is_dir():
        print(
            f"Warning: {name} at '{path}' is a directory, ignoring it and falling back to other configuration sources.",
            file=sys.stderr,
        )
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_settings() -> LoadedSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_config = _read_json_object(CONFIG_FILE, name="config.json")
    auth_key = _resolve_text_setting(raw_config, "auth-key", ENV_AUTH_KEY)
    if _is_invalid_auth_key(auth_key):
        raise ValueError(
            "❌ auth-key 未设置！\n"
            f"请在环境变量 {ENV_AUTH_KEY} 中设置，或者在 config.json 中填写 auth-key。"
        )
    refresh_interval = _resolve_int_setting(
        raw_config,
        "refresh_account_interval_minute",
        ENV_REFRESH_ACCOUNT_INTERVAL_MINUTE,
        DEFAULT_REFRESH_ACCOUNT_INTERVAL_MINUTE,
    )

    return LoadedSettings(
        auth_key=auth_key,
        refresh_account_interval_minute=refresh_interval,
    )


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        if _is_invalid_auth_key(self.auth_key):
            raise ValueError(
                "❌ auth-key 未设置！\n"
                "请按以下任意一种方式解决：\n"
                "1. 在 Render 的 Environment 变量中添加：\n"
                f"   {ENV_AUTH_KEY} = your_real_auth_key\n"
                "2. 或者在 config.json 中填写：\n"
                '   "auth-key": "your_real_auth_key"'
            )

    def _load(self) -> dict[str, object]:
        return _read_json_object(self.path, name="config.json")

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @property
    def auth_key(self) -> str:
        return _resolve_text_setting(self.data, "auth-key", ENV_AUTH_KEY)

    @property
    def accounts_file(self) -> Path:
        return DATA_DIR / "accounts.json"

    @property
    def refresh_account_interval_minute(self) -> int:
        return _resolve_int_setting(
            self.data,
            "refresh_account_interval_minute",
            ENV_REFRESH_ACCOUNT_INTERVAL_MINUTE,
            DEFAULT_REFRESH_ACCOUNT_INTERVAL_MINUTE,
        )

    @property
    def images_dir(self) -> Path:
        path = DATA_DIR / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def base_url(self) -> str:
        return _resolve_text_setting(self.data, "base_url", ENV_BASE_URL).rstrip("/")

    @property
    def app_version(self) -> str:
        try:
            value = VERSION_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "0.0.0"
        return value or "0.0.0"

    def get(self) -> dict[str, object]:
        return dict(self.data)

    def get_proxy_settings(self) -> str:
        return _resolve_text_setting(self.data, "proxy", ENV_PROXY)

    def update(self, data: dict[str, object]) -> dict[str, object]:
        next_data = dict(self.data)
        next_data.update(dict(data or {}))
        if _is_invalid_auth_key(next_data.get("auth-key")):
            next_data["auth-key"] = self.data.get("auth-key") or _read_env_text(ENV_AUTH_KEY) or ""
        self.data = next_data
        self._save()
        return self.get()


config = ConfigStore(CONFIG_FILE)
