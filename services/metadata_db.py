from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any

from services.config import DATA_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MetadataDatabase:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (DATA_DIR / "metadata.sqlite3")
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    saved_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    type TEXT,
                    status TEXT,
                    quota INTEGER,
                    image_quota_unknown INTEGER,
                    email TEXT,
                    user_id TEXT,
                    default_model_slug TEXT,
                    restore_at TEXT,
                    success INTEGER,
                    fail INTEGER,
                    last_used_at TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS async_jobs (
                    job_id TEXT PRIMARY KEY,
                    type TEXT,
                    status TEXT,
                    model TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    api_key_id TEXT,
                    api_key_name TEXT,
                    prompt_preview TEXT,
                    requested_count INTEGER,
                    size TEXT,
                    input_image_count INTEGER,
                    result_ready INTEGER,
                    result_count INTEGER,
                    error_message TEXT,
                    log_path TEXT,
                    result_path TEXT,
                    preview_images_json TEXT,
                    payload_json TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_logs (
                    job_id TEXT PRIMARY KEY,
                    log_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS system_files (
                    kind TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    api_key_id TEXT,
                    api_key_name TEXT,
                    model TEXT,
                    request_id TEXT,
                    payload_hint TEXT
                );
                """
            )

    def record_settings(self, payload: dict[str, Any]) -> None:
        saved_at = _utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO settings_snapshots(saved_at, payload_json) VALUES(?, ?)",
                (saved_at, payload_json),
            )

    def record_accounts(self, accounts: list[dict[str, Any]]) -> None:
        updated_at = _utc_now()
        with self._lock, self._connect() as connection:
            current_ids = [str(item.get("id") or "").strip() for item in accounts if str(item.get("id") or "").strip()]
            connection.execute("DELETE FROM accounts")
            for item in accounts:
                account_id = str(item.get("id") or "").strip()
                if not account_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO accounts(
                        account_id, access_token, type, status, quota, image_quota_unknown, email, user_id,
                        default_model_slug, restore_at, success, fail, last_used_at, payload_json, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        str(item.get("access_token") or ""),
                        str(item.get("type") or ""),
                        str(item.get("status") or ""),
                        int(item.get("quota") or 0),
                        1 if item.get("imageQuotaUnknown") else 0,
                        str(item.get("email") or "") or None,
                        str(item.get("user_id") or "") or None,
                        str(item.get("default_model_slug") or "") or None,
                        str(item.get("restoreAt") or "") or None,
                        int(item.get("success") or 0),
                        int(item.get("fail") or 0),
                        str(item.get("lastUsedAt") or "") or None,
                        json.dumps(item, ensure_ascii=False),
                        updated_at,
                    ),
                )
            if not current_ids:
                connection.execute("DELETE FROM accounts")

    def record_async_job(
            self,
            public_job: dict[str, Any],
            *,
            payload: dict[str, Any] | None = None,
            preview_images: list[dict[str, Any]] | None = None,
            result_path: str | None = None,
    ) -> None:
        recorded_at = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO async_jobs(
                    job_id, type, status, model, created_at, updated_at, api_key_id, api_key_name,
                    prompt_preview, requested_count, size, input_image_count, result_ready, result_count,
                    error_message, log_path, result_path, preview_images_json, payload_json, recorded_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    type=excluded.type,
                    status=excluded.status,
                    model=excluded.model,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    api_key_id=excluded.api_key_id,
                    api_key_name=excluded.api_key_name,
                    prompt_preview=excluded.prompt_preview,
                    requested_count=excluded.requested_count,
                    size=excluded.size,
                    input_image_count=excluded.input_image_count,
                    result_ready=excluded.result_ready,
                    result_count=excluded.result_count,
                    error_message=excluded.error_message,
                    log_path=excluded.log_path,
                    result_path=excluded.result_path,
                    preview_images_json=excluded.preview_images_json,
                    payload_json=excluded.payload_json,
                    recorded_at=excluded.recorded_at
                """,
                (
                    str(public_job.get("id") or ""),
                    str(public_job.get("type") or ""),
                    str(public_job.get("status") or ""),
                    str(public_job.get("model") or ""),
                    str(public_job.get("created_at") or ""),
                    str(public_job.get("updated_at") or ""),
                    str(public_job.get("api_key_id") or "") or None,
                    str(public_job.get("api_key_name") or "") or None,
                    str(public_job.get("prompt_preview") or "") or None,
                    int(public_job.get("requested_count") or 0),
                    str(public_job.get("size") or "") or None,
                    int(public_job.get("input_image_count") or 0),
                    1 if public_job.get("result_ready") else 0,
                    int(public_job.get("result_count") or 0),
                    str(((public_job.get("error") or {}) if isinstance(public_job.get("error"), dict) else {}).get("message") or "") or None,
                    str(public_job.get("log_path") or "") or None,
                    str(result_path or "") or None,
                    json.dumps(preview_images or [], ensure_ascii=False),
                    json.dumps(payload or {}, ensure_ascii=False),
                    recorded_at,
                ),
            )

    def record_task_log(self, job_id: str, log_path: str) -> None:
        updated_at = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_logs(job_id, log_path, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    log_path=excluded.log_path,
                    updated_at=excluded.updated_at
                """,
                (job_id, log_path, updated_at),
            )

    def record_system_file(self, kind: str, file_path: str) -> None:
        updated_at = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_files(kind, file_path, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(kind) DO UPDATE SET
                    file_path=excluded.file_path,
                    updated_at=excluded.updated_at
                """,
                (kind, file_path, updated_at),
            )

    def record_request_log(
            self,
            *,
            method: str,
            path: str,
            status_code: int,
            duration_ms: float,
            api_key_id: str | None = None,
            api_key_name: str | None = None,
            model: str | None = None,
            request_id: str | None = None,
            payload_hint: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO request_logs(
                    created_at, method, path, status_code, duration_ms, api_key_id, api_key_name, model, request_id, payload_hint
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    method,
                    path,
                    status_code,
                    duration_ms,
                    api_key_id,
                    api_key_name,
                    model,
                    request_id,
                    payload_hint,
                ),
            )


metadata_db = MetadataDatabase()
