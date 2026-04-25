from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
import mimetypes
from pathlib import Path
import re
from threading import Lock
from time import time
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageOps

from services.config import DATA_DIR, config

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_IMAGE_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),
]
_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_THUMBNAIL_MAX_SIZE = (512, 512)


def _thumbnail_file_name(file_name: str) -> str:
    path = Path(file_name)
    return f"{path.stem}-thumb{path.suffix}"


def _image_format_for_extension(extension: str) -> str:
    normalized = extension.lower()
    if normalized in {".jpg", ".jpeg"}:
        return "JPEG"
    if normalized == ".webp":
        return "WEBP"
    if normalized == ".gif":
        return "GIF"
    return "PNG"


def _create_thumbnail_bytes(image_data: bytes, extension: str) -> bytes:
    with Image.open(BytesIO(image_data)) as source_image:
        working = ImageOps.exif_transpose(source_image)
        thumbnail = working.copy()
        thumbnail.thumbnail(_THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
        image_format = _image_format_for_extension(extension)
        if image_format == "JPEG":
            if thumbnail.mode not in {"RGB", "L"}:
                thumbnail = thumbnail.convert("RGB")
        elif image_format == "PNG" and thumbnail.mode == "P":
            thumbnail = thumbnail.convert("RGBA")
        output = BytesIO()
        thumbnail.save(output, format=image_format)
        return output.getvalue()


def _normalize_id(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return text.strip("-") or "image-task"


def _guess_extension(image_data: bytes, mime_type: str | None = None) -> str:
    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime in _MIME_EXTENSIONS:
        return _MIME_EXTENSIONS[normalized_mime]
    for signature, extension in _IMAGE_SIGNATURES:
        if image_data.startswith(signature):
            if extension == ".webp" and len(image_data) >= 12 and image_data[8:12] != b"WEBP":
                continue
            return extension
    return ".png"


def build_image_url(date_segment: str, file_name: str, base_url: str | None = None) -> str:
    path = f"/api/view/data/{date_segment}/{file_name}"
    prefix = str(base_url or config.base_url or "").strip().rstrip("/")
    return f"{prefix}{path}" if prefix else path


def save_image_bytes(
        image_data: bytes,
        *,
        request_id: str,
        image_index: int,
        base_url: str | None = None,
        mime_type: str | None = None,
) -> dict[str, str]:
    date_segment = datetime.now().strftime("%Y-%m-%d")
    extension = _guess_extension(image_data, mime_type)
    file_name = f"{_normalize_id(request_id)}-{max(1, int(image_index))}{extension}"
    thumbnail_file_name = _thumbnail_file_name(file_name)
    target_dir = DATA_DIR / date_segment
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    thumbnail_path = target_dir / thumbnail_file_name
    target_path.write_bytes(image_data)
    try:
        thumbnail_bytes = _create_thumbnail_bytes(image_data, extension)
    except Exception:
        thumbnail_bytes = image_data
    thumbnail_path.write_bytes(thumbnail_bytes)
    image_url = build_image_url(date_segment, file_name, base_url)
    thumbnail_url = build_image_url(date_segment, thumbnail_file_name, base_url)
    return {
        "date": date_segment,
        "file_name": file_name,
        "relative_path": f"{date_segment}/{file_name}",
        "url": image_url,
        "thumbnail_file_name": thumbnail_file_name,
        "thumbnail_relative_path": f"{date_segment}/{thumbnail_file_name}",
        "thumbnail_url": thumbnail_url,
        "markdown": f"[![image]({thumbnail_url})]({image_url})",
    }


def resolve_image_path(date_segment: str, file_name: str) -> Path:
    if not _DATE_DIR_RE.fullmatch(date_segment):
        raise HTTPException(status_code=404, detail={"error": "image not found"})
    clean_name = Path(file_name).name
    if clean_name != file_name or clean_name in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail={"error": "image not found"})
    path = DATA_DIR / date_segment / clean_name
    try:
        path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "image not found"}) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"error": "image not found"})
    return path


def guess_media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class DataMaintenanceService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._last_run_at = 0.0

    @staticmethod
    def _iter_image_files() -> list[Path]:
        items: list[Path] = []
        if not DATA_DIR.exists():
            return items
        for child in DATA_DIR.iterdir():
            if child.is_dir() and _DATE_DIR_RE.fullmatch(child.name):
                items.extend(path for path in child.iterdir() if path.is_file())
        return items

    @staticmethod
    def _directory_stats(path: Path) -> dict[str, Any]:
        if path.is_file():
            return {"path": str(path), "files": 1, "bytes": path.stat().st_size}
        files = 0
        total_bytes = 0
        if path.exists():
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    files += 1
                    total_bytes += file_path.stat().st_size
        return {"path": str(path), "files": files, "bytes": total_bytes}

    def collect_stats(self) -> dict[str, Any]:
        categories = {
            "system_logs": self._directory_stats(config.system_log_file),
            "task_logs": self._directory_stats(config.task_logs_dir),
            "images": {
                "path": str(DATA_DIR),
                "files": 0,
                "bytes": 0,
            },
            "jobs": self._directory_stats(config.jobs_dir),
            "job_results": self._directory_stats(config.job_results_dir),
            "placeholders": self._directory_stats(config.image_placeholder_dir),
        }
        image_files = self._iter_image_files()
        categories["images"]["files"] = len(image_files)
        categories["images"]["bytes"] = sum(path.stat().st_size for path in image_files)
        known_bytes = sum(int(item["bytes"]) for item in categories.values())
        known_files = sum(int(item["files"]) for item in categories.values())
        total_files = 0
        total_bytes = 0
        if DATA_DIR.exists():
            for file_path in DATA_DIR.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_bytes += file_path.stat().st_size
        categories["other"] = {
            "path": str(DATA_DIR),
            "files": max(0, total_files - known_files),
            "bytes": max(0, total_bytes - known_bytes),
        }
        return {
            "root": str(DATA_DIR),
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "total_files": total_files,
            "total_bytes": total_bytes,
            "categories": categories,
        }

    @staticmethod
    def _delete_older_than(paths: list[Path], *, retention_days: int, now: datetime) -> tuple[int, int]:
        if retention_days <= 0:
            return 0, 0
        deleted_files = 0
        deleted_bytes = 0
        cutoff = now - timedelta(days=retention_days)
        for path in paths:
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified_at >= cutoff:
                continue
            try:
                file_size = path.stat().st_size
                path.unlink()
                deleted_files += 1
                deleted_bytes += file_size
            except OSError:
                continue
        return deleted_files, deleted_bytes

    @staticmethod
    def _cleanup_empty_image_dirs() -> int:
        removed_dirs = 0
        if not DATA_DIR.exists():
            return removed_dirs
        for child in DATA_DIR.iterdir():
            if not child.is_dir() or not _DATE_DIR_RE.fullmatch(child.name):
                continue
            try:
                next(child.iterdir())
            except StopIteration:
                try:
                    child.rmdir()
                    removed_dirs += 1
                except OSError:
                    continue
        return removed_dirs

    @staticmethod
    def _truncate_system_log(max_megabytes: int) -> dict[str, int]:
        path = config.system_log_file
        if not path.is_file():
            return {"before_bytes": 0, "after_bytes": 0, "trimmed_bytes": 0}
        limit_bytes = max(1, max_megabytes) * 1024 * 1024
        before_bytes = path.stat().st_size
        if before_bytes <= limit_bytes:
            return {"before_bytes": before_bytes, "after_bytes": before_bytes, "trimmed_bytes": 0}
        payload = path.read_bytes()
        truncated = payload[-limit_bytes:]
        path.write_bytes(truncated)
        return {
            "before_bytes": before_bytes,
            "after_bytes": len(truncated),
            "trimmed_bytes": max(0, before_bytes - len(truncated)),
        }

    def cleanup(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if not force and not config.data_cleanup_enabled:
                return {
                    "enabled": False,
                    "stats": self.collect_stats(),
                    "deleted": {"images": 0, "task_logs": 0, "empty_image_dirs": 0},
                    "system_log": self._truncate_system_log(config.system_log_max_mb),
                }

            now = datetime.now()
            image_files = self._iter_image_files()
            task_log_files = [path for path in config.task_logs_dir.glob("*.log") if path.is_file()]
            deleted_image_files, deleted_image_bytes = self._delete_older_than(
                image_files,
                retention_days=config.image_retention_days,
                now=now,
            )
            deleted_task_log_files, deleted_task_log_bytes = self._delete_older_than(
                task_log_files,
                retention_days=config.task_log_retention_days,
                now=now,
            )
            empty_image_dirs = self._cleanup_empty_image_dirs()
            system_log = self._truncate_system_log(config.system_log_max_mb)
            self._last_run_at = time()
            from utils.log import logger

            logger.info({
                "event": "data_cleanup_completed",
                "deleted_image_files": deleted_image_files,
                "deleted_task_log_files": deleted_task_log_files,
                "empty_image_dirs": empty_image_dirs,
                "system_log_trimmed_bytes": system_log["trimmed_bytes"],
            })
            return {
                "enabled": True,
                "run_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "deleted": {
                    "images": {"files": deleted_image_files, "bytes": deleted_image_bytes},
                    "task_logs": {"files": deleted_task_log_files, "bytes": deleted_task_log_bytes},
                    "empty_image_dirs": empty_image_dirs,
                },
                "system_log": system_log,
                "stats": self.collect_stats(),
            }

    def run_if_due(self) -> dict[str, Any] | None:
        interval_seconds = max(1, config.data_cleanup_interval_minutes) * 60
        if self._last_run_at and time() - self._last_run_at < interval_seconds:
            return None
        return self.cleanup(force=False)


data_maintenance_service = DataMaintenanceService()
