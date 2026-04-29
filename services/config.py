from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_DATA_DIR = "CHATGPT2API_DATA_DIR"
ENV_CONFIG_FILE = "CHATGPT2API_CONFIG_FILE"


def _resolve_startup_path(env_name: str, default: Path) -> Path:
    raw_value = str(os.getenv(env_name) or "").strip()
    if not raw_value:
        return default
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


DATA_DIR = _resolve_startup_path(ENV_DATA_DIR, BASE_DIR / "data")
CONFIG_FILE = _resolve_startup_path(ENV_CONFIG_FILE, DATA_DIR / "config.json")
LEGACY_CONFIG_FILE = BASE_DIR / "config.json"
VERSION_FILE = BASE_DIR / "VERSION"
DEFAULT_REFRESH_ACCOUNT_INTERVAL_MINUTE = 5
DEFAULT_LISTEN_PORT = 80
DEFAULT_IMAGE_FAILURE_STRATEGY = "fail"
DEFAULT_IMAGE_STORAGE_BACKEND = "local"
DEFAULT_IMAGE_RETRY_COUNT = 0
DEFAULT_IMAGE_PARALLEL_ATTEMPTS = 1
DEFAULT_IMAGE_RESPONSE_FORMAT = "b64_json"
DEFAULT_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED = False
DEFAULT_IMAGE_THUMBNAIL_MAX_SIZE = 512
DEFAULT_IMAGE_THUMBNAIL_QUALITY = 85
DEFAULT_IMAGE_WALL_THUMBNAIL_MAX_SIZE = 960
DEFAULT_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED = True
DEFAULT_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED = True
DEFAULT_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED = True
DEFAULT_IMAGE_RETENTION_DAYS = 7
DEFAULT_TASK_LOG_RETENTION_DAYS = 7
DEFAULT_SYSTEM_LOG_MAX_MB = 32
DEFAULT_DATA_CLEANUP_ENABLED = False
DEFAULT_DATA_CLEANUP_INTERVAL_MINUTES = 60
ENV_AUTH_KEY = "CHATGPT2API_AUTH_KEY"
ENV_REFRESH_ACCOUNT_INTERVAL_MINUTE = "CHATGPT2API_REFRESH_ACCOUNT_INTERVAL_MINUTE"
ENV_PROXY = "CHATGPT2API_PROXY"
ENV_BASE_URL = "CHATGPT2API_BASE_URL"
ENV_PORT = "CHATGPT2API_PORT"
ENV_PLATFORM_PORT = "PORT"
ENV_IMAGE_FAILURE_STRATEGY = "CHATGPT2API_IMAGE_FAILURE_STRATEGY"
ENV_IMAGE_STORAGE_BACKEND = "CHATGPT2API_IMAGE_STORAGE_BACKEND"
ENV_IMAGE_HF_DATASET_REPO = "CHATGPT2API_IMAGE_HF_DATASET_REPO"
ENV_IMAGE_HF_DATASET_PATH = "CHATGPT2API_IMAGE_HF_DATASET_PATH"
ENV_IMAGE_HF_TOKEN = "CHATGPT2API_IMAGE_HF_TOKEN"
ENV_IMAGE_HF_DATASET_URL = "CHATGPT2API_IMAGE_HF_DATASET_URL"
ENV_IMAGE_RETRY_COUNT = "CHATGPT2API_IMAGE_RETRY_COUNT"
ENV_IMAGE_PARALLEL_ATTEMPTS = "CHATGPT2API_IMAGE_PARALLEL_ATTEMPTS"
ENV_IMAGE_PLACEHOLDER_PATH = "CHATGPT2API_IMAGE_PLACEHOLDER_PATH"
ENV_IMAGE_RESPONSE_FORMAT = "CHATGPT2API_IMAGE_RESPONSE_FORMAT"
ENV_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED = "CHATGPT2API_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED"
ENV_IMAGE_URL_PREFIX = "CHATGPT2API_IMAGE_URL_PREFIX"
ENV_IMAGE_URL_TEMPLATE = "CHATGPT2API_IMAGE_URL_TEMPLATE"
ENV_IMAGE_THUMBNAIL_MAX_SIZE = "CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE"
ENV_IMAGE_THUMBNAIL_QUALITY = "CHATGPT2API_IMAGE_THUMBNAIL_QUALITY"
ENV_IMAGE_WALL_THUMBNAIL_MAX_SIZE = "CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE"
ENV_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED = "CHATGPT2API_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED"
ENV_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED = "CHATGPT2API_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED"
ENV_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED = "CHATGPT2API_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED"
ENV_IMAGE_RETENTION_DAYS = "CHATGPT2API_IMAGE_RETENTION_DAYS"
ENV_TASK_LOG_RETENTION_DAYS = "CHATGPT2API_TASK_LOG_RETENTION_DAYS"
ENV_SYSTEM_LOG_MAX_MB = "CHATGPT2API_SYSTEM_LOG_MAX_MB"
ENV_DATA_CLEANUP_ENABLED = "CHATGPT2API_DATA_CLEANUP_ENABLED"
ENV_DATA_CLEANUP_INTERVAL_MINUTES = "CHATGPT2API_DATA_CLEANUP_INTERVAL_MINUTES"

ENV_OVERRIDABLE_SETTINGS = {
    "auth-key": ENV_AUTH_KEY,
    "refresh_account_interval_minute": ENV_REFRESH_ACCOUNT_INTERVAL_MINUTE,
    "proxy": ENV_PROXY,
    "base_url": ENV_BASE_URL,
    "port": ENV_PORT,
    "image_storage_backend": ENV_IMAGE_STORAGE_BACKEND,
    "image_hf_dataset_repo": ENV_IMAGE_HF_DATASET_REPO,
    "image_hf_dataset_path": ENV_IMAGE_HF_DATASET_PATH,
    "image_hf_token": ENV_IMAGE_HF_TOKEN,
    "image_hf_dataset_url": ENV_IMAGE_HF_DATASET_URL,
    "image_failure_strategy": ENV_IMAGE_FAILURE_STRATEGY,
    "image_retry_count": ENV_IMAGE_RETRY_COUNT,
    "image_parallel_attempts": ENV_IMAGE_PARALLEL_ATTEMPTS,
    "image_placeholder_path": ENV_IMAGE_PLACEHOLDER_PATH,
    "image_response_format": ENV_IMAGE_RESPONSE_FORMAT,
    "image_url_include_b64_when_requested": ENV_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED,
    "image_url_prefix": ENV_IMAGE_URL_PREFIX,
    "image_url_template": ENV_IMAGE_URL_TEMPLATE,
    "image_thumbnail_max_size": ENV_IMAGE_THUMBNAIL_MAX_SIZE,
    "image_thumbnail_quality": ENV_IMAGE_THUMBNAIL_QUALITY,
    "image_wall_thumbnail_max_size": ENV_IMAGE_WALL_THUMBNAIL_MAX_SIZE,
    "openai_compat_image_task_tracking_enabled": ENV_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED,
    "openai_compat_image_gallery_enabled": ENV_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED,
    "openai_compat_image_waterfall_enabled": ENV_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED,
    "image_retention_days": ENV_IMAGE_RETENTION_DAYS,
    "task_log_retention_days": ENV_TASK_LOG_RETENTION_DAYS,
    "system_log_max_mb": ENV_SYSTEM_LOG_MAX_MB,
    "data_cleanup_enabled": ENV_DATA_CLEANUP_ENABLED,
    "data_cleanup_interval_minutes": ENV_DATA_CLEANUP_INTERVAL_MINUTES,
}


@dataclass(frozen=True)
class LoadedSettings:
    auth_key: str
    refresh_account_interval_minute: int
    port: int


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


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _normalize_text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


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


def _resolve_bounded_int_setting(
        raw_config: dict[str, object],
        key: str,
        env_name: str,
        default: int,
        *,
        min_value: int,
        max_value: int,
) -> int:
    value = _resolve_int_setting(raw_config, key, env_name, default)
    if value < min_value or value > max_value:
        return default
    return value


def _resolve_bool_setting(raw_config: dict[str, object], key: str, env_name: str, default: bool) -> bool:
    env_value = _parse_bool(os.getenv(env_name))
    if env_value is not None:
        return env_value
    file_value = _parse_bool(raw_config.get(key))
    if file_value is not None:
        return file_value
    return default


def _resolve_choice_setting(
        raw_config: dict[str, object],
        key: str,
        env_name: str,
        default: str,
        choices: set[str],
) -> str:
    env_value = _read_env_text(env_name).lower()
    if env_value in choices:
        return env_value
    file_value = _normalize_text(raw_config.get(key)).lower()
    if file_value in choices:
        return file_value
    return default


def _resolve_path_setting(raw_config: dict[str, object], key: str, env_name: str) -> Path | None:
    raw_value = _resolve_text_setting(raw_config, key, env_name)
    if not raw_value:
        return None
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


def _parse_port(value: object) -> int | None:
    port = _parse_int(value)
    if port is None or not 1 <= port <= 65535:
        return None
    return port


def _resolve_port_setting(raw_config: dict[str, object], key: str = "port") -> int:
    for env_name in (ENV_PORT, ENV_PLATFORM_PORT):
        port = _parse_port(os.getenv(env_name))
        if port is not None:
            return port
    file_port = _parse_port(raw_config.get(key))
    if file_port is not None:
        return file_port
    return DEFAULT_LISTEN_PORT


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


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return left.absolute() == right.absolute()


def _load_config_data(path: Path) -> dict[str, object]:
    data = _read_json_object(path, name="config.json")
    if data or path.exists() or _same_path(path, LEGACY_CONFIG_FILE):
        return data
    return _read_json_object(LEGACY_CONFIG_FILE, name="legacy config.json")


def _load_settings() -> LoadedSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_config = _load_config_data(CONFIG_FILE)
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
    port = _resolve_port_setting(raw_config)

    return LoadedSettings(
        auth_key=auth_key,
        refresh_account_interval_minute=refresh_interval,
        port=port,
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
        data = _load_config_data(self.path)
        if data and not self.path.exists() and not _same_path(self.path, LEGACY_CONFIG_FILE):
            self.data = data
            self._save(record_metadata=False)
        return data

    def _save(self, *, record_metadata: bool = True) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not record_metadata:
            return
        try:
            from services.metadata_db import metadata_db

            metadata_db.record_settings(self.get())
        except Exception:
            pass

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
    def image_placeholder_dir(self) -> Path:
        path = DATA_DIR / "placeholders"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def base_url(self) -> str:
        return _resolve_text_setting(self.data, "base_url", ENV_BASE_URL).rstrip("/")

    @property
    def image_url_prefix(self) -> str:
        return _resolve_text_setting(self.data, "image_url_prefix", ENV_IMAGE_URL_PREFIX).rstrip("/")

    @property
    def image_url_template(self) -> str:
        return _resolve_text_setting(self.data, "image_url_template", ENV_IMAGE_URL_TEMPLATE)

    @property
    def listen_port(self) -> int:
        return _resolve_port_setting(self.data)

    @property
    def image_failure_strategy(self) -> str:
        return _resolve_choice_setting(
            self.data,
            "image_failure_strategy",
            ENV_IMAGE_FAILURE_STRATEGY,
            DEFAULT_IMAGE_FAILURE_STRATEGY,
            {"fail", "retry", "placeholder"},
        )

    @property
    def image_storage_backend(self) -> str:
        return _resolve_choice_setting(
            self.data,
            "image_storage_backend",
            ENV_IMAGE_STORAGE_BACKEND,
            DEFAULT_IMAGE_STORAGE_BACKEND,
            {"local", "hf_datasets"},
        )

    @property
    def image_hf_dataset_repo(self) -> str:
        return _resolve_text_setting(self.data, "image_hf_dataset_repo", ENV_IMAGE_HF_DATASET_REPO)

    @property
    def image_hf_dataset_path(self) -> str:
        return _resolve_text_setting(self.data, "image_hf_dataset_path", ENV_IMAGE_HF_DATASET_PATH).strip("/")

    @property
    def image_hf_token(self) -> str:
        return _resolve_text_setting(self.data, "image_hf_token", ENV_IMAGE_HF_TOKEN)

    @property
    def image_hf_dataset_url(self) -> str:
        return _resolve_text_setting(self.data, "image_hf_dataset_url", ENV_IMAGE_HF_DATASET_URL).rstrip("/")

    @property
    def image_retry_count(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_retry_count",
            ENV_IMAGE_RETRY_COUNT,
            DEFAULT_IMAGE_RETRY_COUNT,
            min_value=0,
            max_value=5,
        )

    @property
    def image_parallel_attempts(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_parallel_attempts",
            ENV_IMAGE_PARALLEL_ATTEMPTS,
            DEFAULT_IMAGE_PARALLEL_ATTEMPTS,
            min_value=1,
            max_value=8,
        )

    @property
    def image_placeholder_path(self) -> Path | None:
        return _resolve_path_setting(self.data, "image_placeholder_path", ENV_IMAGE_PLACEHOLDER_PATH)

    @property
    def image_response_format(self) -> str:
        return _resolve_choice_setting(
            self.data,
            "image_response_format",
            ENV_IMAGE_RESPONSE_FORMAT,
            DEFAULT_IMAGE_RESPONSE_FORMAT,
            {"b64_json", "url"},
        )

    @property
    def image_url_include_b64_when_requested(self) -> bool:
        return _resolve_bool_setting(
            self.data,
            "image_url_include_b64_when_requested",
            ENV_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED,
            DEFAULT_IMAGE_URL_INCLUDE_B64_WHEN_REQUESTED,
        )

    @property
    def image_thumbnail_max_size(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_thumbnail_max_size",
            ENV_IMAGE_THUMBNAIL_MAX_SIZE,
            DEFAULT_IMAGE_THUMBNAIL_MAX_SIZE,
            min_value=64,
            max_value=2048,
        )

    @property
    def image_thumbnail_quality(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_thumbnail_quality",
            ENV_IMAGE_THUMBNAIL_QUALITY,
            DEFAULT_IMAGE_THUMBNAIL_QUALITY,
            min_value=1,
            max_value=100,
        )

    @property
    def image_wall_thumbnail_max_size(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_wall_thumbnail_max_size",
            ENV_IMAGE_WALL_THUMBNAIL_MAX_SIZE,
            DEFAULT_IMAGE_WALL_THUMBNAIL_MAX_SIZE,
            min_value=128,
            max_value=4096,
        )

    @property
    def openai_compat_image_task_tracking_enabled(self) -> bool:
        return _resolve_bool_setting(
            self.data,
            "openai_compat_image_task_tracking_enabled",
            ENV_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED,
            DEFAULT_OPENAI_COMPAT_IMAGE_TASK_TRACKING_ENABLED,
        )

    @property
    def openai_compat_image_gallery_enabled(self) -> bool:
        return _resolve_bool_setting(
            self.data,
            "openai_compat_image_gallery_enabled",
            ENV_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED,
            DEFAULT_OPENAI_COMPAT_IMAGE_GALLERY_ENABLED,
        )

    @property
    def openai_compat_image_waterfall_enabled(self) -> bool:
        return _resolve_bool_setting(
            self.data,
            "openai_compat_image_waterfall_enabled",
            ENV_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED,
            DEFAULT_OPENAI_COMPAT_IMAGE_WATERFALL_ENABLED,
        )

    @property
    def image_retention_days(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "image_retention_days",
            ENV_IMAGE_RETENTION_DAYS,
            DEFAULT_IMAGE_RETENTION_DAYS,
            min_value=0,
            max_value=365,
        )

    @property
    def task_log_retention_days(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "task_log_retention_days",
            ENV_TASK_LOG_RETENTION_DAYS,
            DEFAULT_TASK_LOG_RETENTION_DAYS,
            min_value=0,
            max_value=365,
        )

    @property
    def system_log_max_mb(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "system_log_max_mb",
            ENV_SYSTEM_LOG_MAX_MB,
            DEFAULT_SYSTEM_LOG_MAX_MB,
            min_value=1,
            max_value=1024,
        )

    @property
    def data_cleanup_enabled(self) -> bool:
        return _resolve_bool_setting(
            self.data,
            "data_cleanup_enabled",
            ENV_DATA_CLEANUP_ENABLED,
            DEFAULT_DATA_CLEANUP_ENABLED,
        )

    @property
    def data_cleanup_interval_minutes(self) -> int:
        return _resolve_bounded_int_setting(
            self.data,
            "data_cleanup_interval_minutes",
            ENV_DATA_CLEANUP_INTERVAL_MINUTES,
            DEFAULT_DATA_CLEANUP_INTERVAL_MINUTES,
            min_value=1,
            max_value=1440,
        )

    @property
    def api_keys_file(self) -> Path:
        return DATA_DIR / "api_keys.json"

    @property
    def system_log_file(self) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / "system.log"

    @property
    def task_logs_dir(self) -> Path:
        path = DATA_DIR / "task_logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def jobs_dir(self) -> Path:
        path = DATA_DIR / "jobs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def job_results_dir(self) -> Path:
        path = DATA_DIR / "job_results"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def app_version(self) -> str:
        try:
            value = VERSION_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "0.0.0"
        return value or "0.0.0"

    def get(self) -> dict[str, object]:
        return dict(self.data)

    def get_effective(self) -> dict[str, object]:
        effective = dict(self.data)
        effective.update(
            {
                "auth-key": self.auth_key,
                "port": self.listen_port,
                "refresh_account_interval_minute": self.refresh_account_interval_minute,
                "proxy": self.get_proxy_settings(),
                "base_url": self.base_url,
                "image_storage_backend": self.image_storage_backend,
                "image_hf_dataset_repo": self.image_hf_dataset_repo,
                "image_hf_dataset_path": self.image_hf_dataset_path,
                "image_hf_token": self.image_hf_token,
                "image_hf_dataset_url": self.image_hf_dataset_url,
                "image_url_prefix": self.image_url_prefix,
                "image_url_template": self.image_url_template,
                "image_failure_strategy": self.image_failure_strategy,
                "image_retry_count": self.image_retry_count,
                "image_parallel_attempts": self.image_parallel_attempts,
                "image_placeholder_path": str(self.image_placeholder_path or ""),
                "image_response_format": self.image_response_format,
                "image_url_include_b64_when_requested": self.image_url_include_b64_when_requested,
                "image_thumbnail_max_size": self.image_thumbnail_max_size,
                "image_thumbnail_quality": self.image_thumbnail_quality,
                "image_wall_thumbnail_max_size": self.image_wall_thumbnail_max_size,
                "openai_compat_image_task_tracking_enabled": self.openai_compat_image_task_tracking_enabled,
                "openai_compat_image_gallery_enabled": self.openai_compat_image_gallery_enabled,
                "openai_compat_image_waterfall_enabled": self.openai_compat_image_waterfall_enabled,
                "image_retention_days": self.image_retention_days,
                "task_log_retention_days": self.task_log_retention_days,
                "system_log_max_mb": self.system_log_max_mb,
                "data_cleanup_enabled": self.data_cleanup_enabled,
                "data_cleanup_interval_minutes": self.data_cleanup_interval_minutes,
            }
        )
        return effective

    def env_overrides(self) -> dict[str, str]:
        overrides = {
            key: env_name
            for key, env_name in ENV_OVERRIDABLE_SETTINGS.items()
            if _read_env_text(env_name)
        }
        if "port" not in overrides and _read_env_text(ENV_PLATFORM_PORT):
            overrides["port"] = ENV_PLATFORM_PORT
        return overrides

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
