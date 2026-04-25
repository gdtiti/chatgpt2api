from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

from services.config import DATA_DIR

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MetadataDatabase:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (DATA_DIR / "metadata.sqlite3")
        self._lock = RLock()
        self._initializing = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = self._open_connection()
        connection.row_factory = sqlite3.Row
        try:
            try:
                self._verify_connection(connection)
            except sqlite3.DatabaseError as exc:
                connection.close()
                if not self._is_corruption_error(exc):
                    raise
                self._quarantine_corrupt_database(exc)
                self._initialize()
                connection = self._open_connection()
                connection.row_factory = sqlite3.Row
                self._verify_connection(connection)
            if not self._initializing and not self._schema_ready(connection):
                connection.close()
                self._initialize()
                connection = self._open_connection()
                connection.row_factory = sqlite3.Row
                self._verify_connection(connection)
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except sqlite3.DatabaseError:
                pass
            raise
        finally:
            connection.close()

    def _open_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
        message = str(exc).lower()
        return (
            "database disk image is malformed" in message
            or "file is not a database" in message
            or "sqlite integrity check failed" in message
        )

    @staticmethod
    def _verify_connection(connection: sqlite3.Connection) -> None:
        row = connection.execute("PRAGMA quick_check").fetchone()
        result = str(row[0] if row else "").strip()
        if result.lower() != "ok":
            raise sqlite3.DatabaseError(f"sqlite integrity check failed: {result}")

    @staticmethod
    def _schema_ready(connection: sqlite3.Connection) -> bool:
        required_tables = {
            "settings_snapshots",
            "accounts",
            "async_jobs",
            "gallery_images",
            "task_logs",
            "system_files",
            "request_logs",
        }
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN (?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(required_tables),
        ).fetchall()
        existing_tables = {str(row[0]) for row in rows}
        return required_tables.issubset(existing_tables)

    @staticmethod
    def _unique_quarantine_path(path: Path, timestamp: str) -> Path:
        candidate = path.with_name(f"{path.name}.corrupt-{timestamp}")
        if not candidate.exists():
            return candidate
        for index in range(1, 1000):
            indexed = path.with_name(f"{path.name}.corrupt-{timestamp}.{index}")
            if not indexed.exists():
                return indexed
        return path.with_name(f"{path.name}.corrupt-{timestamp}.{datetime.now(timezone.utc).timestamp():.0f}")

    def _quarantine_corrupt_database(self, exc: sqlite3.DatabaseError) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        moved_paths: list[str] = []
        related_paths = [
            self.path,
            self.path.with_name(f"{self.path.name}-wal"),
            self.path.with_name(f"{self.path.name}-shm"),
        ]
        for source in related_paths:
            if not source.exists():
                continue
            target = self._unique_quarantine_path(source, timestamp)
            source.replace(target)
            moved_paths.append(str(target))
        _LOGGER.error(
            "metadata sqlite database was corrupt and has been quarantined",
            extra={"path": str(self.path), "quarantined_paths": moved_paths, "error": str(exc)},
        )

    def _initialize(self) -> None:
        with self._lock:
            previous_initializing = self._initializing
            self._initializing = True
            try:
                with self._connect() as connection:
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
                        CREATE TABLE IF NOT EXISTS gallery_images (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL,
                            image_index INTEGER NOT NULL,
                            image_id TEXT,
                            type TEXT,
                            model TEXT,
                            prompt_preview TEXT,
                            created_at TEXT,
                            updated_at TEXT,
                            api_key_id TEXT,
                            api_key_name TEXT,
                            src TEXT NOT NULL,
                            url TEXT,
                            thumbnail_url TEXT,
                            relative_path TEXT,
                            thumbnail_relative_path TEXT,
                            wall_url TEXT,
                            wall_relative_path TEXT,
                            markdown TEXT,
                            is_recommended INTEGER NOT NULL DEFAULT 0,
                            is_pinned INTEGER NOT NULL DEFAULT 0,
                            is_blocked INTEGER NOT NULL DEFAULT 0,
                            payload_json TEXT,
                            recorded_at TEXT NOT NULL,
                            UNIQUE(job_id, image_index)
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
                        CREATE INDEX IF NOT EXISTS idx_async_jobs_scope_updated ON async_jobs(api_key_id, updated_at);
                        CREATE INDEX IF NOT EXISTS idx_async_jobs_updated ON async_jobs(updated_at);
                        CREATE INDEX IF NOT EXISTS idx_async_jobs_scope_status_updated ON async_jobs(api_key_id, status, updated_at);
                        CREATE INDEX IF NOT EXISTS idx_async_jobs_status_type ON async_jobs(status, type);
                        CREATE INDEX IF NOT EXISTS idx_gallery_scope_updated ON gallery_images(api_key_id, updated_at);
                        CREATE INDEX IF NOT EXISTS idx_gallery_updated ON gallery_images(updated_at);
                        CREATE INDEX IF NOT EXISTS idx_gallery_job_index ON gallery_images(job_id, image_index);
                        CREATE INDEX IF NOT EXISTS idx_gallery_job_updated ON gallery_images(job_id, updated_at);
                        CREATE INDEX IF NOT EXISTS idx_gallery_wall_order ON gallery_images(is_blocked, is_pinned, is_recommended, updated_at, id);
                        CREATE INDEX IF NOT EXISTS idx_gallery_scope_wall_order ON gallery_images(api_key_id, is_blocked, is_pinned, is_recommended, updated_at, id);
                        """
                    )
                    self._ensure_column(connection, "gallery_images", "relative_path", "TEXT")
                    self._ensure_column(connection, "gallery_images", "thumbnail_relative_path", "TEXT")
                    self._ensure_column(connection, "gallery_images", "wall_url", "TEXT")
                    self._ensure_column(connection, "gallery_images", "wall_relative_path", "TEXT")
                    self._ensure_column(connection, "gallery_images", "is_recommended", "INTEGER NOT NULL DEFAULT 0")
                    self._ensure_column(connection, "gallery_images", "is_pinned", "INTEGER NOT NULL DEFAULT 0")
                    self._ensure_column(connection, "gallery_images", "is_blocked", "INTEGER NOT NULL DEFAULT 0")
            finally:
                self._initializing = previous_initializing

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    @staticmethod
    def _decode_json_object(value: object) -> dict[str, Any]:
        try:
            payload = json.loads(str(value or "{}"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _decode_json_list(value: object) -> list[dict[str, Any]]:
        try:
            payload = json.loads(str(value or "[]"))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _safe_sort(value: str | None, allowed: set[str], default: str) -> str:
        candidate = str(value or "").strip()
        return candidate if candidate in allowed else default

    @staticmethod
    def _row_to_public_job(row: sqlite3.Row) -> dict[str, Any]:
        preview_images = MetadataDatabase._decode_json_list(row["preview_images_json"])
        error_message = str(row["error_message"] or "").strip()
        return {
            "id": row["job_id"],
            "type": row["type"],
            "status": row["status"],
            "model": row["model"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "log_path": row["log_path"],
            "api_key_id": row["api_key_id"],
            "api_key_name": row["api_key_name"],
            "prompt_preview": row["prompt_preview"],
            "requested_count": int(row["requested_count"] or 0),
            "size": row["size"],
            "input_image_count": int(row["input_image_count"] or 0),
            "result_ready": bool(row["result_ready"]),
            "result_count": int(row["result_count"] or 0),
            "preview_images": preview_images,
            "error": {"message": error_message} if error_message else None,
        }

    @staticmethod
    def _append_job_filters(
            where: list[str],
            params: list[Any],
            *,
            is_admin: bool,
            api_key_id: str,
            status: str | None = None,
            job_type: str | None = None,
            query: str | None = None,
    ) -> None:
        if not is_admin:
            where.append("api_key_id = ?")
            params.append(api_key_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if job_type:
            where.append("type = ?")
            params.append(job_type)
        if query:
            like = f"%{query}%"
            where.append(
                "(job_id LIKE ? OR type LIKE ? OR model LIKE ? OR prompt_preview LIKE ? OR api_key_name LIKE ?)"
            )
            params.extend([like, like, like, like, like])

    @staticmethod
    def _where_sql(where: list[str]) -> str:
        return f"WHERE {' AND '.join(where)}" if where else ""

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
            self._record_gallery_images_locked(
                connection,
                public_job,
                preview_images or [],
                payload or {},
                recorded_at=recorded_at,
            )

    def _record_gallery_images_locked(
            self,
            connection: sqlite3.Connection,
            public_job: dict[str, Any],
            preview_images: list[dict[str, Any]],
            payload: dict[str, Any],
            *,
            recorded_at: str,
    ) -> None:
        job_id = str(public_job.get("id") or "").strip()
        if not job_id:
            return
        existing_states = {
            int(row["image_index"]): {
                "is_recommended": int(row["is_recommended"] or 0),
                "is_pinned": int(row["is_pinned"] or 0),
                "is_blocked": int(row["is_blocked"] or 0),
            }
            for row in connection.execute(
                "SELECT image_index, is_recommended, is_pinned, is_blocked FROM gallery_images WHERE job_id = ?",
                (job_id,),
            ).fetchall()
        }
        connection.execute("DELETE FROM gallery_images WHERE job_id = ?", (job_id,))
        if not preview_images:
            return
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        for index, item in enumerate(preview_images, start=1):
            src = str(item.get("src") or item.get("thumbnail_url") or item.get("url") or "").strip()
            if not src:
                continue
            state = existing_states.get(index, {})
            connection.execute(
                """
                INSERT INTO gallery_images(
                    job_id, image_index, image_id, type, model, prompt_preview, created_at, updated_at,
                    api_key_id, api_key_name, src, url, thumbnail_url, relative_path, thumbnail_relative_path,
                    wall_url, wall_relative_path, markdown, is_recommended, is_pinned, is_blocked,
                    payload_json, recorded_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, image_index) DO UPDATE SET
                    image_id=excluded.image_id,
                    type=excluded.type,
                    model=excluded.model,
                    prompt_preview=excluded.prompt_preview,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    api_key_id=excluded.api_key_id,
                    api_key_name=excluded.api_key_name,
                    src=excluded.src,
                    url=excluded.url,
                    thumbnail_url=excluded.thumbnail_url,
                    relative_path=excluded.relative_path,
                    thumbnail_relative_path=excluded.thumbnail_relative_path,
                    wall_url=excluded.wall_url,
                    wall_relative_path=excluded.wall_relative_path,
                    markdown=excluded.markdown,
                    payload_json=excluded.payload_json,
                    recorded_at=excluded.recorded_at
                """,
                (
                    job_id,
                    index,
                    str(item.get("id") or "") or None,
                    str(public_job.get("type") or ""),
                    str(public_job.get("model") or ""),
                    str(public_job.get("prompt_preview") or "") or None,
                    str(public_job.get("created_at") or "") or None,
                    str(public_job.get("updated_at") or "") or None,
                    str(public_job.get("api_key_id") or "") or None,
                    str(public_job.get("api_key_name") or "") or None,
                    src,
                    str(item.get("url") or "") or None,
                    str(item.get("thumbnail_url") or "") or None,
                    str(item.get("relative_path") or "") or None,
                    str(item.get("thumbnail_relative_path") or "") or None,
                    str(item.get("wall_url") or "") or None,
                    str(item.get("wall_relative_path") or "") or None,
                    str(item.get("markdown") or "") or None,
                    int(state.get("is_recommended") or 0),
                    int(state.get("is_pinned") or 0),
                    int(state.get("is_blocked") or 0),
                    payload_json,
                    recorded_at,
                ),
            )

    def list_async_jobs(
            self,
            *,
            is_admin: bool,
            api_key_id: str,
            limit: int = 50,
            offset: int = 0,
            status: str | None = None,
            job_type: str | None = None,
            query: str | None = None,
            sort: str | None = None,
            order: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        limit_value = max(1, min(int(limit or 50), 200))
        offset_value = max(0, int(offset or 0))
        sort_column = self._safe_sort(sort, {"created_at", "updated_at", "status", "type", "model"}, "updated_at")
        direction = "ASC" if str(order or "").lower() == "asc" else "DESC"
        where: list[str] = []
        params: list[Any] = []
        self._append_job_filters(
            where,
            params,
            is_admin=is_admin,
            api_key_id=api_key_id,
            status=str(status or "").strip() or None,
            job_type=str(job_type or "").strip() or None,
            query=str(query or "").strip() or None,
        )
        where_sql = self._where_sql(where)
        with self._lock, self._connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM async_jobs {where_sql}", params).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT * FROM async_jobs
                {where_sql}
                ORDER BY {sort_column} {direction}, job_id {direction}
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
        return [self._row_to_public_job(row) for row in rows], total

    def has_async_jobs(self, *, is_admin: bool, api_key_id: str) -> bool:
        where: list[str] = []
        params: list[Any] = []
        if not is_admin:
            where.append("api_key_id = ?")
            params.append(api_key_id)
        where_sql = self._where_sql(where)
        with self._lock, self._connect() as connection:
            row = connection.execute(f"SELECT 1 FROM async_jobs {where_sql} LIMIT 1", params).fetchone()
        return row is not None

    def summarize_async_jobs(self, *, is_admin: bool, api_key_id: str) -> dict[str, int]:
        where: list[str] = []
        params: list[Any] = []
        if not is_admin:
            where.append("api_key_id = ?")
            params.append(api_key_id)
        where_sql = self._where_sql(where)
        summary = {
            "total": 0,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
        }
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT status, COUNT(*) AS count FROM async_jobs {where_sql} GROUP BY status",
                params,
            ).fetchall()
        for row in rows:
            count = int(row["count"] or 0)
            summary["total"] += count
            status = str(row["status"] or "")
            if status in summary:
                summary[status] = count
        return summary

    def list_gallery_jobs(
            self,
            *,
            is_admin: bool,
            api_key_id: str,
            limit: int = 20,
            offset: int = 0,
            query: str | None = None,
            sort: str | None = None,
            order: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        limit_value = max(1, min(int(limit or 20), 100))
        offset_value = max(0, int(offset or 0))
        sort_column = self._safe_sort(sort, {"created_at", "updated_at", "model", "type"}, "updated_at")
        direction = "ASC" if str(order or "").lower() == "asc" else "DESC"
        where: list[str] = []
        params: list[Any] = []
        if not is_admin:
            where.append("api_key_id = ?")
            params.append(api_key_id)
        cleaned_query = str(query or "").strip()
        if cleaned_query:
            like = f"%{cleaned_query}%"
            where.append("(job_id LIKE ? OR model LIKE ? OR prompt_preview LIKE ? OR api_key_name LIKE ?)")
            params.extend([like, like, like, like])
        where_sql = self._where_sql(where)
        with self._lock, self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM (SELECT job_id FROM gallery_images {where_sql} GROUP BY job_id)",
                    params,
                ).fetchone()[0]
            )
            job_rows = connection.execute(
                f"""
                SELECT
                    job_id,
                    MAX(type) AS type,
                    MAX(model) AS model,
                    MAX(prompt_preview) AS prompt_preview,
                    MIN(created_at) AS created_at,
                    MAX(updated_at) AS updated_at,
                    MAX(api_key_id) AS api_key_id,
                    MAX(api_key_name) AS api_key_name,
                    COUNT(*) AS result_count
                FROM gallery_images
                {where_sql}
                GROUP BY job_id
                ORDER BY {sort_column} {direction}, job_id {direction}
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
            job_ids = [str(row["job_id"]) for row in job_rows]
            image_rows: list[sqlite3.Row] = []
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                image_rows = connection.execute(
                    f"""
                    SELECT * FROM gallery_images
                    WHERE job_id IN ({placeholders})
                    ORDER BY job_id, image_index ASC
                    """,
                    job_ids,
                ).fetchall()
        images_by_job: dict[str, list[dict[str, Any]]] = {}
        for row in image_rows:
            job_id = str(row["job_id"])
            image = {
                "id": row["image_id"] or f"{job_id}-{row['image_index']}",
                "src": row["src"],
                "url": row["url"],
                "thumbnail_url": row["thumbnail_url"],
                "relative_path": row["relative_path"],
                "thumbnail_relative_path": row["thumbnail_relative_path"],
                "wall_url": row["wall_url"],
                "wall_relative_path": row["wall_relative_path"],
                "is_recommended": bool(row["is_recommended"]),
                "is_pinned": bool(row["is_pinned"]),
                "is_blocked": bool(row["is_blocked"]),
                "markdown": row["markdown"],
            }
            images_by_job.setdefault(job_id, []).append(image)
        items: list[dict[str, Any]] = []
        for row in job_rows:
            job_id = str(row["job_id"])
            items.append({
                "id": job_id,
                "type": row["type"],
                "status": "succeeded",
                "model": row["model"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "log_path": None,
                "api_key_id": row["api_key_id"],
                "api_key_name": row["api_key_name"],
                "prompt_preview": row["prompt_preview"],
                "requested_count": int(row["result_count"] or 0),
                "size": None,
                "input_image_count": 0,
                "result_ready": True,
                "result_count": int(row["result_count"] or 0),
                "preview_images": images_by_job.get(job_id, []),
                "error": None,
            })
        return items, total

    def list_waterfall_images(
            self,
            *,
            is_admin: bool,
            api_key_id: str,
            limit: int = 40,
            offset: int = 0,
            query: str | None = None,
            include_blocked: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        limit_value = max(1, min(int(limit or 40), 100))
        offset_value = max(0, int(offset or 0))
        where: list[str] = []
        params: list[Any] = []
        if not is_admin:
            where.append("api_key_id = ?")
            params.append(api_key_id)
        if not include_blocked:
            where.append("is_blocked = 0")
        cleaned_query = str(query or "").strip()
        if cleaned_query:
            like = f"%{cleaned_query}%"
            where.append("(job_id LIKE ? OR model LIKE ? OR prompt_preview LIKE ? OR api_key_name LIKE ?)")
            params.extend([like, like, like, like])
        where_sql = self._where_sql(where)
        with self._lock, self._connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM gallery_images {where_sql}", params).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT * FROM gallery_images
                {where_sql}
                ORDER BY is_pinned DESC, is_recommended DESC, updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            job_id = str(row["job_id"])
            items.append({
                "id": row["image_id"] or f"{job_id}-{row['image_index']}",
                "job_id": job_id,
                "image_index": int(row["image_index"] or 0),
                "type": row["type"],
                "model": row["model"],
                "prompt_preview": row["prompt_preview"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "api_key_id": row["api_key_id"],
                "api_key_name": row["api_key_name"],
                "src": row["src"],
                "url": row["url"],
                "thumbnail_url": row["thumbnail_url"],
                "relative_path": row["relative_path"],
                "thumbnail_relative_path": row["thumbnail_relative_path"],
                "wall_url": row["wall_url"],
                "wall_relative_path": row["wall_relative_path"],
                "markdown": row["markdown"],
                "is_recommended": bool(row["is_recommended"]),
                "is_pinned": bool(row["is_pinned"]),
                "is_blocked": bool(row["is_blocked"]),
            })
        return items, total

    def update_gallery_image_state(
            self,
            *,
            job_id: str,
            image_index: int,
            is_recommended: bool | None = None,
            is_pinned: bool | None = None,
            is_blocked: bool | None = None,
    ) -> dict[str, Any] | None:
        assignments: list[str] = []
        params: list[Any] = []
        if is_recommended is not None:
            assignments.append("is_recommended = ?")
            params.append(1 if is_recommended else 0)
        if is_pinned is not None:
            assignments.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if is_blocked is not None:
            assignments.append("is_blocked = ?")
            params.append(1 if is_blocked else 0)
        if not assignments:
            return None
        params.extend([job_id, image_index])
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE gallery_images SET {', '.join(assignments)} WHERE job_id = ? AND image_index = ?",
                params,
            )
            row = connection.execute(
                "SELECT * FROM gallery_images WHERE job_id = ? AND image_index = ?",
                (job_id, image_index),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["image_id"] or f"{row['job_id']}-{row['image_index']}",
            "job_id": row["job_id"],
            "image_index": int(row["image_index"] or 0),
            "src": row["src"],
            "url": row["url"],
            "thumbnail_url": row["thumbnail_url"],
            "wall_url": row["wall_url"],
            "relative_path": row["relative_path"],
            "thumbnail_relative_path": row["thumbnail_relative_path"],
            "wall_relative_path": row["wall_relative_path"],
            "is_recommended": bool(row["is_recommended"]),
            "is_pinned": bool(row["is_pinned"]),
            "is_blocked": bool(row["is_blocked"]),
        }

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
