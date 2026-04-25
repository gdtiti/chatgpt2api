import base64
import binascii
import contextvars
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DEFAULT_SYSTEM_LOG_FILE = DATA_DIR / "system.log"
_TASK_LOG_PATH: contextvars.ContextVar[Path | None] = contextvars.ContextVar("chatgpt2api_task_log_path", default=None)


class _TaskLogContext:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._token: contextvars.Token[Path | None] | None = None

    def __enter__(self) -> Path | None:
        self._token = _TASK_LOG_PATH.set(self._path)
        return self._path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _TASK_LOG_PATH.reset(self._token)


class Logger:
    _DATA_URL_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")
    _JSON_B64_RE = re.compile(r'("b64_json"\s*:\s*")([A-Za-z0-9+/=]+)(")')

    def __init__(self, name: str = "chatgpt2api") -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._file_lock = Lock()
        self._system_log_path = DEFAULT_SYSTEM_LOG_FILE

    @property
    def system_log_path(self) -> Path:
        return self._system_log_path

    def set_system_log_path(self, path: Path) -> None:
        self._system_log_path = Path(path)

    def task_context(self, path: Path | None) -> _TaskLogContext:
        return _TaskLogContext(Path(path) if path else None)

    def _mask_string(self, value: str, keep: int = 10) -> str:
        if len(value) <= keep:
            return value
        return value[:keep] + "..."

    def _mask_base64(self, value: str) -> str:
        if value.startswith("data:") and ";base64," in value:
            header, _, data = value.partition(",")
            return f"{header},{self._mask_string(data, 24)} (base64 len={len(data)})"
        return f"{self._mask_string(value, 24)} (base64 len={len(value)})"

    def _is_base64_string(self, value: str) -> bool:
        if len(value) < 64 or len(value) % 4 != 0:
            return False
        if not any(char in value for char in "+/="):
            return False
        try:
            base64.b64decode(value, validate=True)
            return True
        except (binascii.Error, ValueError):
            return False

    def _sanitize_string(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("data:") and ";base64," in stripped:
            return self._mask_base64(stripped)
        if self._is_base64_string(stripped):
            return self._mask_base64(stripped)
        sanitized = self._DATA_URL_RE.sub(lambda match: self._mask_base64(match.group(0)), value)
        sanitized = self._JSON_B64_RE.sub(
            lambda match: f'{match.group(1)}{self._mask_base64(match.group(2))}{match.group(3)}',
            sanitized,
        )
        if sanitized != value:
            return sanitized
        return value

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                lowered_key = key.lower()
                if isinstance(item, str) and ("token" in lowered_key or lowered_key == "dx"):
                    sanitized[key] = self._mask_string(item)
                elif isinstance(item, str) and ("base64" in lowered_key or lowered_key == "b64_json"):
                    sanitized[key] = self._mask_base64(item)
                else:
                    sanitized[key] = self._sanitize(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._sanitize(item) for item in value)
        if isinstance(value, str):
            return self._sanitize_string(value)
        return value

    def _serialize(self, value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except TypeError:
                return str(value)
        return str(value)

    def _append_file_log(self, path: Path, level: str, message: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        line = f"{timestamp} [{level}] {self._serialize(message)}\n"
        with self._file_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _emit(self, level: str, message: Any) -> None:
        sanitized = self._sanitize(message)
        getattr(self._logger, level.lower())(sanitized)
        self._append_file_log(self._system_log_path, level, sanitized)
        task_log_path = _TASK_LOG_PATH.get()
        if task_log_path is not None:
            self._append_file_log(task_log_path, level, sanitized)

    def debug(self, message: Any) -> None:
        self._emit("DEBUG", message)

    def info(self, message: Any) -> None:
        self._emit("INFO", message)

    def warning(self, message: Any) -> None:
        self._emit("WARNING", message)

    def error(self, message: Any) -> None:
        self._emit("ERROR", message)


logger = Logger()
