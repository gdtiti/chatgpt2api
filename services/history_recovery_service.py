from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from services.config import config
from services.data_service import build_image_url
from services.metadata_db import metadata_db

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_RECOVERABLE_JOB_EVENTS = {
    "async_job_submitted": "queued",
    "async_job_started": "running",
    "async_job_succeeded": "succeeded",
    "async_job_failed": "failed",
    "inline_job_started": "running",
    "inline_job_succeeded": "succeeded",
    "inline_job_failed": "failed",
}
_LOG_LINE_RE = re.compile(r"^(?P<time>\S+)\s+\[(?P<level>[A-Z]+)]\s+(?P<payload>\{.*})\s*$")
_IMAGE_STEM_RE = re.compile(r"^(?P<job_id>.+)-(?P<image_index>\d+)$")


def _utc_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _prompt_preview(payload: dict[str, Any], fallback: str = "recovered/unknown") -> str:
    prompt = str(payload.get("prompt") or "").strip()
    if prompt:
        return " ".join(prompt.split())[:240]
    input_value = payload.get("input")
    if isinstance(input_value, str) and input_value.strip():
        return " ".join(input_value.split())[:240]
    return fallback


def _thumbnail_name(file_name: str, suffix: str) -> str:
    path = Path(file_name)
    return f"{path.stem}-{suffix}{path.suffix}"


def _image_item_from_file(path: Path, *, job_id: str, image_index: int, created_at: str) -> dict[str, Any]:
    date_segment = path.parent.name
    file_name = path.name
    thumb_name = _thumbnail_name(file_name, "thumb")
    wall_name = _thumbnail_name(file_name, "wall")
    thumb_path = path.with_name(thumb_name)
    wall_path = path.with_name(wall_name)
    relative_path = f"{date_segment}/{file_name}"
    thumbnail_relative_path = f"{date_segment}/{thumb_name}" if thumb_path.is_file() else relative_path
    wall_relative_path = f"{date_segment}/{wall_name}" if wall_path.is_file() else thumbnail_relative_path
    url = build_image_url(date_segment, file_name, config.base_url or None)
    thumbnail_url = build_image_url(date_segment, thumb_name, config.base_url or None) if thumb_path.is_file() else url
    wall_url = build_image_url(date_segment, wall_name, config.base_url or None) if wall_path.is_file() else thumbnail_url
    payload = {
        "prompt": "recovered/unknown",
        "recovered": True,
        "recovery_source": "images",
        "relative_path": relative_path,
    }
    return {
        "id": f"{job_id}-{image_index}",
        "job_id": job_id,
        "image_index": image_index,
        "type": "images.generations",
        "model": "recovered",
        "prompt_preview": "recovered/unknown",
        "created_at": created_at,
        "updated_at": created_at,
        "api_key_id": "recovered",
        "api_key_name": "recovered",
        "src": thumbnail_url,
        "url": url,
        "thumbnail_url": thumbnail_url,
        "relative_path": relative_path,
        "thumbnail_relative_path": thumbnail_relative_path,
        "wall_url": wall_url,
        "wall_relative_path": wall_relative_path,
        "markdown": f"[![image]({thumbnail_url})]({url})",
        "payload": payload,
    }


def _extract_job_id_from_log_name(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        return stem.rsplit("_", 1)[-1]
    return stem


def _iter_log_events(path: Path, *, max_lines: int = 20000) -> list[tuple[str, str, dict[str, Any]]]:
    if not path.is_file():
        return []
    events: list[tuple[str, str, dict[str, Any]]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    for line in lines[-max_lines:]:
        match = _LOG_LINE_RE.match(line)
        if not match:
            continue
        try:
            payload = json.loads(match.group("payload"))
        except Exception:
            continue
        if isinstance(payload, dict):
            events.append((match.group("time"), match.group("level"), payload))
    return events


def _extract_preview_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    payload = result.get("result") if isinstance(result.get("result"), dict) else result
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        src = str(item.get("thumbnail_url") or item.get("url") or item.get("src") or "").strip()
        if not src:
            continue
        next_item = dict(item)
        next_item.setdefault("id", f"image-{index}")
        next_item.setdefault("src", src)
        items.append(next_item)
    return items


class HistoryRecoveryService:
    def scan(self) -> dict[str, Any]:
        snapshot = metadata_db.recovery_snapshot()
        existing_jobs: set[str] = set(snapshot["async_job_ids"])
        existing_gallery_keys: set[tuple[str, int]] = set(snapshot["gallery_keys"])
        existing_relative_paths: set[str] = set(snapshot["gallery_relative_paths"])
        existing_task_logs: set[str] = set(snapshot["task_log_ids"])
        seen_task_log_ids = set(existing_task_logs)

        jobs_by_id: dict[str, dict[str, Any]] = {}
        gallery_items: list[dict[str, Any]] = []
        task_logs: list[dict[str, Any]] = []
        source_counts = {
            "job_files": 0,
            "result_files": 0,
            "task_log_files": 0,
            "system_log_events": 0,
            "image_original_files": 0,
        }
        seen_gallery_keys = set(existing_gallery_keys)
        seen_relative_paths = set(existing_relative_paths)

        for path in sorted(config.jobs_dir.glob("*.json")):
            job = _read_json_file(path)
            job_id = str(job.get("id") or path.stem).strip()
            if not job_id:
                continue
            payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            result_path = config.job_results_dir / f"{job_id}.json"
            result = _read_json_file(result_path) if result_path.is_file() else {}
            preview_images = _extract_preview_images(result)
            public_job = {
                "id": job_id,
                "type": str(job.get("type") or "images.generations"),
                "status": str(job.get("status") or ("succeeded" if result else "queued")),
                "model": str(job.get("model") or payload.get("model") or "recovered"),
                "created_at": str(job.get("created_at") or _utc_from_mtime(path)),
                "updated_at": str(job.get("updated_at") or _utc_from_mtime(path)),
                "log_path": str(job.get("log_path") or "") or None,
                "api_key_id": str(job.get("api_key_id") or "recovered"),
                "api_key_name": str(job.get("api_key_name") or "recovered"),
                "prompt_preview": _prompt_preview(payload),
                "requested_count": int(payload.get("n") or len(preview_images) or 1),
                "size": str(payload.get("size") or "") or None,
                "input_image_count": 0,
                "result_ready": bool(result),
                "result_count": len(preview_images),
                "preview_images": preview_images,
                "payload": payload,
                "result": result if result else None,
                "result_path": str(result_path) if result else None,
            }
            jobs_by_id.setdefault(job_id, public_job)
            source_counts["job_files"] += 1
            if result:
                source_counts["result_files"] += 1

        log_paths = list(config.task_logs_dir.glob("*.log"))
        for path in sorted(log_paths):
            job_id = _extract_job_id_from_log_name(path)
            if not job_id:
                continue
            updated_at = _utc_from_mtime(path)
            if job_id not in seen_task_log_ids:
                task_logs.append({"job_id": job_id, "log_path": str(path), "updated_at": updated_at})
                seen_task_log_ids.add(job_id)
            jobs_by_id.setdefault(job_id, {
                "id": job_id,
                "type": "images.generations",
                "status": "succeeded",
                "model": "recovered",
                "created_at": updated_at,
                "updated_at": updated_at,
                "log_path": str(path),
                "api_key_id": "recovered",
                "api_key_name": "recovered",
                "prompt_preview": "recovered/unknown",
                "requested_count": 1,
                "result_ready": False,
                "result_count": 0,
                "payload": {"prompt": "recovered/unknown", "recovered": True, "recovery_source": "task_logs"},
            })
            source_counts["task_log_files"] += 1

        for event_time, _level, payload in _iter_log_events(config.system_log_file):
            event = str(payload.get("event") or "")
            status = _RECOVERABLE_JOB_EVENTS.get(event)
            job_id = str(payload.get("job_id") or "").strip()
            if not status or not job_id:
                continue
            current = jobs_by_id.get(job_id, {})
            next_job = {
                "id": job_id,
                "type": str(payload.get("job_type") or current.get("type") or "images.generations"),
                "status": status,
                "model": str(payload.get("model") or current.get("model") or "recovered"),
                "created_at": str(current.get("created_at") or event_time),
                "updated_at": event_time,
                "log_path": str(payload.get("log_path") or current.get("log_path") or "") or None,
                "api_key_id": str(payload.get("api_key_id") or current.get("api_key_id") or "recovered"),
                "api_key_name": str(payload.get("api_key_name") or current.get("api_key_name") or "recovered"),
                "prompt_preview": str(current.get("prompt_preview") or "recovered/unknown"),
                "requested_count": int(current.get("requested_count") or payload.get("result_count") or 1),
                "result_ready": status == "succeeded" or bool(current.get("result_ready")),
                "result_count": int(payload.get("result_count") or current.get("result_count") or 0),
                "payload": current.get("payload") if isinstance(current.get("payload"), dict) else {
                    "prompt": "recovered/unknown",
                    "recovered": True,
                    "recovery_source": "system_log",
                },
                "error": {"message": str(payload.get("error"))} if payload.get("error") else None,
            }
            jobs_by_id[job_id] = next_job
            if next_job["log_path"] and job_id not in seen_task_log_ids:
                task_logs.append({"job_id": job_id, "log_path": next_job["log_path"], "updated_at": event_time})
                seen_task_log_ids.add(job_id)
            source_counts["system_log_events"] += 1

        image_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for date_dir in sorted(config.images_dir.iterdir() if config.images_dir.exists() else []):
            if not date_dir.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir.name):
                continue
            for path in sorted(date_dir.iterdir()):
                if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                if path.stem.endswith("-thumb") or path.stem.endswith("-wall"):
                    continue
                source_counts["image_original_files"] += 1
                relative_path = f"{date_dir.name}/{path.name}"
                if relative_path in seen_relative_paths:
                    continue
                match = _IMAGE_STEM_RE.match(path.stem)
                base_job_id = match.group("job_id") if match else f"recovered-image-{hashlib.sha1(relative_path.encode('utf-8')).hexdigest()[:16]}"
                image_index = int(match.group("image_index")) if match else 1
                job_id = base_job_id
                if (job_id, image_index) in seen_gallery_keys:
                    job_id = f"recovered-{date_dir.name}-{path.stem}"
                    image_index = 1
                seen_gallery_keys.add((job_id, image_index))
                seen_relative_paths.add(relative_path)
                created_at = _utc_from_mtime(path)
                item = _image_item_from_file(path, job_id=job_id, image_index=image_index, created_at=created_at)
                gallery_items.append(item)
                image_groups[job_id].append(item)

        for job_id, items in image_groups.items():
            first = items[0]
            jobs_by_id.setdefault(job_id, {
                "id": job_id,
                "type": "images.generations",
                "status": "succeeded",
                "model": "recovered",
                "created_at": first["created_at"],
                "updated_at": max(str(item["updated_at"]) for item in items),
                "api_key_id": "recovered",
                "api_key_name": "recovered",
                "prompt_preview": "recovered/unknown",
                "requested_count": len(items),
                "result_ready": True,
                "result_count": len(items),
                "preview_images": [
                    {
                        "id": item["id"],
                        "src": item["src"],
                        "url": item["url"],
                        "thumbnail_url": item["thumbnail_url"],
                        "wall_url": item["wall_url"],
                        "relative_path": item["relative_path"],
                        "thumbnail_relative_path": item["thumbnail_relative_path"],
                        "wall_relative_path": item["wall_relative_path"],
                        "markdown": item["markdown"],
                    }
                    for item in items
                ],
                "payload": {
                    "prompt": "recovered/unknown",
                    "recovered": True,
                    "recovery_source": "images",
                },
            })

        candidate_jobs = [job for job_id, job in jobs_by_id.items() if job_id not in existing_jobs]
        return {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "existing": snapshot["counts"],
            "candidates": {
                "async_jobs": len(candidate_jobs),
                "gallery_images": len(gallery_items),
                "task_logs": len(task_logs),
            },
            "source_counts": source_counts,
            "samples": {
                "jobs": [str(item.get("id")) for item in candidate_jobs[:10]],
                "images": [str(item.get("relative_path")) for item in gallery_items[:10]],
                "task_logs": [str(item.get("log_path")) for item in task_logs[:10]],
            },
            "_records": {
                "jobs": candidate_jobs,
                "gallery_images": gallery_items,
                "task_logs": task_logs,
            },
        }

    def scan_report(self) -> dict[str, Any]:
        report = self.scan()
        return {key: value for key, value in report.items() if key != "_records"}

    def apply(self) -> dict[str, Any]:
        report = self.scan()
        records = report.get("_records") if isinstance(report.get("_records"), dict) else {}
        inserted = metadata_db.recover_records(
            jobs=list(records.get("jobs") or []),
            gallery_images=list(records.get("gallery_images") or []),
            task_logs=list(records.get("task_logs") or []),
        )
        next_report = self.scan_report()
        return {
            "applied_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "inserted": inserted,
            "before": {key: value for key, value in report.items() if key != "_records"},
            "after": next_report,
        }


history_recovery_service = HistoryRecoveryService()
