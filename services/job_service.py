from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any
from uuid import uuid4

from services.api_key_service import AuthPrincipal
from services.chatgpt_service import ChatGPTService, image_error_code
from services.config import config
from services.image_options import normalize_image_quality, normalize_image_size
from services.data_service import ensure_preview_image_metadata
from utils.log import logger


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _timestamp_for_filename(value: object) -> str:
    raw = _clean_text(value)
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    compact = raw.replace("-", "").replace(":", "").replace(".", "")
    compact = compact.replace("+0000", "Z").replace("+00:00", "Z")
    compact = compact.replace("T", "T").replace("Z", "Z")
    return "".join(char for char in compact if char.isalnum() or char in {"T", "Z"}) or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _coerce_positive_int(value: object, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _truncate_text(value: str, limit: int = 72) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _extract_text_from_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and str(item.get("type") or "") == "text":
            text = _clean_text(item.get("text"))
            if text:
                parts.append(text)
    return " ".join(parts)


def _build_prompt_preview(payload: dict[str, object]) -> str | None:
    prompt = _clean_text(payload.get("prompt"))
    if prompt:
        return _truncate_text(prompt)
    input_value = payload.get("input")
    if isinstance(input_value, str) and input_value.strip():
        return _truncate_text(input_value)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return None
    for item in reversed(messages):
        if not isinstance(item, dict) or str(item.get("role") or "") != "user":
            continue
        content = _extract_text_from_message_content(item.get("content"))
        if content:
            return _truncate_text(content)
    return None


def _count_input_images(images_value: object) -> int:
    if isinstance(images_value, str):
        return 1 if _clean_text(images_value) else 0
    if not isinstance(images_value, list):
        return 0
    return sum(1 for item in images_value if _clean_text(item))


def _count_result_items(result: dict[str, object] | None) -> int:
    if not isinstance(result, dict):
        return 0
    value = result.get("result")
    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            return len(value["data"])
        if isinstance(value.get("choices"), list):
            return len(value["choices"])
        if isinstance(value.get("output"), list):
            return len(value["output"])
        return 1
    if value is None:
        return 0
    return 1


def _error_payload(error: object, *, default_status_code: int = 500) -> dict[str, object]:
    message = str(error or "job failed")
    status_code = int(getattr(error, "status_code", default_status_code) or default_status_code)
    code = str(getattr(error, "code", "") or image_error_code(message))
    return {
        "message": message,
        "code": code,
        "status_code": status_code,
    }


def _is_probable_image_url(value: str) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    return text.startswith(("http://", "https://", "/api/view/data/", "/api/images/", "data:image/"))


def _preview_image_from_item(item: dict[str, object], index: int) -> dict[str, object] | None:
    thumbnail_url = _clean_text(item.get("thumbnail_url"))
    image_url = _clean_text(item.get("url"))
    markdown = _clean_text(item.get("markdown"))
    b64_json = _clean_text(item.get("b64_json"))
    result_value = _clean_text(item.get("result"))
    src = thumbnail_url or image_url
    if not src:
        if b64_json:
            src = f"data:image/png;base64,{b64_json}"
        elif result_value.startswith("data:image/"):
            src = result_value
        elif result_value and not _is_probable_image_url(result_value):
            src = f"data:image/png;base64,{result_value}"
        elif _is_probable_image_url(result_value):
            src = result_value
    if not src:
        return None
    preview = {
        "id": _clean_text(item.get("id")) or f"preview-{index}",
        "src": src,
        "url": image_url or (src if _is_probable_image_url(src) and not src.startswith("data:image/") else None),
        "thumbnail_url": thumbnail_url or None,
        "markdown": markdown or None,
    }
    for key in (
            "relative_path",
            "thumbnail_relative_path",
            "wall_relative_path",
            "file_name",
            "thumbnail_file_name",
            "wall_file_name",
            "wall_url",
    ):
        value = _clean_text(item.get(key))
        if value:
            preview[key] = value
    return ensure_preview_image_metadata(preview, base_url=config.base_url or None)


def _preview_images_from_markdown(markdown: str, start_index: int = 1) -> list[dict[str, object]]:
    previews: list[dict[str, object]] = []
    for index, match in enumerate(re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown or ""), start=start_index):
        src = _clean_text(match.group(1))
        if not src:
            continue
        previews.append(
            ensure_preview_image_metadata(
                {
                    "id": f"preview-{index}",
                    "src": src,
                    "url": src if _is_probable_image_url(src) and not src.startswith("data:image/") else None,
                    "thumbnail_url": src if _is_probable_image_url(src) and not src.startswith("data:image/") else None,
                    "markdown": match.group(0),
                },
                base_url=config.base_url or None,
            )
        )
    return previews


def _extract_preview_images(result: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(result, dict):
        return []
    payload = result.get("result")
    if not isinstance(payload, dict):
        return []
    previews: list[dict[str, object]] = []
    data_items = payload.get("data")
    if isinstance(data_items, list):
        for index, item in enumerate(data_items, start=1):
            if isinstance(item, dict) and (preview := _preview_image_from_item(item, index)) is not None:
                previews.append(preview)
    output_items = payload.get("output")
    if isinstance(output_items, list):
        for index, item in enumerate(output_items, start=1):
            if not isinstance(item, dict) or _clean_text(item.get("type")) != "image_generation_call":
                continue
            if (preview := _preview_image_from_item(item, index)) is not None:
                previews.append(preview)
    choices = payload.get("choices")
    if isinstance(choices, list):
        next_index = len(previews) + 1
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            markdown = _clean_text(message.get("content"))
            extracted = _preview_images_from_markdown(markdown, next_index)
            previews.extend(extracted)
            next_index += len(extracted)
    return previews


def _decode_async_image_payload(images_value: object) -> list[tuple[bytes, str, str]]:
    normalized: list[tuple[bytes, str, str]] = []
    if isinstance(images_value, str):
        images = [images_value]
    elif isinstance(images_value, list):
        images = images_value
    else:
        images = []
    for index, item in enumerate(images, start=1):
        data_url = _clean_text(item)
        if not data_url:
            continue
        mime_type = "image/png"
        raw_data = data_url
        if data_url.startswith("data:"):
            header, _, payload = data_url.partition(",")
            mime_type = header.split(";")[0].removeprefix("data:") or mime_type
            raw_data = payload
        import base64
        normalized.append((base64.b64decode(raw_data), f"image-{index}.png", mime_type))
    return normalized


class JobService:
    def __init__(
            self,
            jobs_dir: Path,
            job_results_dir: Path,
            chatgpt_service: ChatGPTService,
            *,
            task_logs_dir: Path | None = None,
            max_workers: int = 4,
    ):
        self.jobs_dir = jobs_dir
        self.job_results_dir = job_results_dir
        self.task_logs_dir = task_logs_dir or (jobs_dir.parent / "task_logs")
        self.chatgpt_service = chatgpt_service
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.job_results_dir.mkdir(parents=True, exist_ok=True)
        self.task_logs_dir.mkdir(parents=True, exist_ok=True)
        from services.metadata_db import MetadataDatabase, metadata_db

        metadata_path = self.jobs_dir.parent / "metadata.sqlite3"
        self.metadata_db = metadata_db if metadata_db.path == metadata_path else MetadataDatabase(metadata_path)
        self._lock = Lock()
        self._metadata_backfill_attempted_scopes: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="async-job")

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _result_file(self, job_id: str) -> Path:
        return self.job_results_dir / f"{job_id}.json"

    def _task_log_file(self, created_at: object, job_id: str) -> Path:
        return self.task_logs_dir / f"{_timestamp_for_filename(created_at)}_{job_id}.log"

    @staticmethod
    def _read_json(path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _public_job(job: dict[str, object], result: dict[str, object] | None = None) -> dict[str, object]:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        return {
            "id": job.get("id"),
            "type": job.get("type"),
            "status": job.get("status"),
            "model": job.get("model"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "log_path": job.get("log_path"),
            "api_key_id": job.get("api_key_id"),
            "api_key_name": job.get("api_key_name"),
            "prompt_preview": _build_prompt_preview(payload),
            "requested_count": _coerce_positive_int(payload.get("n"), 1),
            "size": _clean_text(payload.get("size")) or None,
            "input_image_count": _count_input_images(payload.get("images") or payload.get("image")),
            "result_ready": result is not None,
            "result_count": _count_result_items(result),
            "preview_images": _extract_preview_images(result),
            "error": job.get("error"),
        }

    @staticmethod
    def _ensure_public_job_previews(public_job: dict[str, object]) -> dict[str, object]:
        preview_images = public_job.get("preview_images")
        if not isinstance(preview_images, list):
            return public_job
        ensured = [
            ensure_preview_image_metadata(item, base_url=config.base_url or None) if isinstance(item, dict) else item
            for item in preview_images
        ]
        next_job = dict(public_job)
        next_job["preview_images"] = ensured
        return next_job

    def _load_job(self, job_id: str) -> dict[str, object] | None:
        return self._read_json(self._job_file(job_id))

    def _load_result(self, job_id: str) -> dict[str, object] | None:
        return self._read_json(self._result_file(job_id))

    def _store_partial_image_result(self, job: dict[str, object], chunk: dict[str, object]) -> None:
        job_id = str(job.get("id") or "")
        if not job_id:
            return
        data = chunk.get("data")
        if not isinstance(data, list):
            return
        image_items = [item for item in data if isinstance(item, dict)]
        if not image_items:
            return
        result_file = self._result_file(job_id)
        current_payload = self._load_result(job_id) or {}
        current_result = current_payload.get("result") if isinstance(current_payload, dict) else None
        current_result = current_result if isinstance(current_result, dict) else {}
        current_data = current_result.get("data") if isinstance(current_result.get("data"), list) else []
        next_result = dict(current_result)
        next_result["created"] = next_result.get("created") or chunk.get("created")
        next_result["data"] = [item for item in current_data if isinstance(item, dict)] + image_items
        result_payload = {"result": next_result}
        self._write_json(result_file, result_payload)
        current_job = self._load_job(job_id) or job
        self.metadata_db.record_async_job(
            self._public_job(current_job, result_payload),
            payload=dict(current_job.get("payload") or job.get("payload") or {}),
            preview_images=_extract_preview_images(result_payload),
            result_path=str(result_file),
        )

    def _store_job(self, job: dict[str, object]) -> dict[str, object]:
        self._write_json(self._job_file(str(job.get("id"))), job)
        return job

    def _update_job(self, job_id: str, **updates: object) -> dict[str, object] | None:
        with self._lock:
            current = self._load_job(job_id)
            if current is None:
                return None
            current.update(updates)
            current["updated_at"] = _utc_now()
            self._store_job(current)
            return current

    def _assert_job_access(self, job: dict[str, object] | None, principal: AuthPrincipal) -> dict[str, object] | None:
        if job is None:
            return None
        if principal.is_admin:
            return job
        return job if str(job.get("api_key_id") or "") == principal.key_id else None

    def submit_job(self, job_type: str, payload: dict[str, object], principal: AuthPrincipal) -> dict[str, object]:
        now = _utc_now()
        model = _clean_text(payload.get("model")) or ("gpt-image-2" if job_type.startswith("images.") else "auto")
        job = {
            "id": uuid4().hex,
            "type": _clean_text(job_type),
            "status": "queued",
            "model": model,
            "created_at": now,
            "updated_at": now,
            "log_path": "",
            "api_key_id": principal.key_id,
            "api_key_name": principal.name,
            "payload": dict(payload or {}),
            "error": None,
        }
        job["log_path"] = str(self._task_log_file(now, str(job["id"])))
        with self._lock:
            self._store_job(job)
        with logger.task_context(Path(str(job["log_path"]))):
            logger.info({
                "event": "async_job_submitted",
                "job_id": job["id"],
                "job_type": job["type"],
                "model": job["model"],
                "api_key_id": job["api_key_id"],
                "api_key_name": job["api_key_name"],
                "log_path": job["log_path"],
            })
        public_job = self._public_job(job)
        self.metadata_db.record_task_log(str(job["id"]), str(job["log_path"]))
        self.metadata_db.record_async_job(public_job, payload=dict(payload or {}))
        self._executor.submit(self._run_job, str(job["id"]))
        return public_job

    def start_inline_job(
            self,
            job_type: str,
            payload: dict[str, object],
            principal: AuthPrincipal,
            *,
            include_task_tracking: bool = True,
    ) -> dict[str, object]:
        now = _utc_now()
        model = _clean_text(payload.get("model")) or ("gpt-image-2" if job_type.startswith("images.") else "auto")
        job = {
            "id": uuid4().hex,
            "type": _clean_text(job_type),
            "status": "running",
            "model": model,
            "created_at": now,
            "updated_at": now,
            "log_path": "",
            "api_key_id": principal.key_id,
            "api_key_name": principal.name,
            "payload": dict(payload or {}),
            "error": None,
            "include_task_tracking": bool(include_task_tracking),
        }
        job["log_path"] = str(self._task_log_file(now, str(job["id"])))
        with self._lock:
            self._store_job(job)
        with logger.task_context(Path(str(job["log_path"]))):
            logger.info({
                "event": "inline_job_started",
                "job_id": job["id"],
                "job_type": job["type"],
                "model": job["model"],
                "api_key_id": job["api_key_id"],
                "api_key_name": job["api_key_name"],
                "log_path": job["log_path"],
            })
        public_job = self._public_job(job)
        self.metadata_db.record_task_log(str(job["id"]), str(job["log_path"]))
        self.metadata_db.record_async_job(
            public_job,
            payload=dict(payload or {}),
            include_task_tracking=include_task_tracking,
        )
        return public_job

    def finish_inline_job(
            self,
            job_id: str,
            result: dict[str, object],
            *,
            include_gallery: bool = True,
            include_waterfall: bool = True,
    ) -> None:
        result_payload = {"result": result}
        result_file = self._result_file(job_id)
        self._write_json(result_file, result_payload)
        succeeded = self._update_job(job_id, status="succeeded", error=None)
        if succeeded is None:
            return
        with logger.task_context(Path(str(succeeded.get("log_path") or self._task_log_file(succeeded.get("created_at"), job_id)))):
            logger.info({
                "event": "inline_job_succeeded",
                "job_id": job_id,
                "result_count": _count_result_items(result_payload),
            })
        self.metadata_db.record_async_job(
            self._public_job(succeeded, result_payload),
            payload=dict(succeeded.get("payload") or {}),
            preview_images=_extract_preview_images(result_payload),
            result_path=str(result_file),
            include_task_tracking=bool(succeeded.get("include_task_tracking", True)),
            include_gallery=include_gallery,
            include_waterfall=include_waterfall,
        )

    def fail_inline_job(self, job_id: str, error: object) -> None:
        failed = self._update_job(job_id, status="failed", error=_error_payload(error, default_status_code=502))
        if failed is None:
            return
        with logger.task_context(Path(str(failed.get("log_path") or self._task_log_file(failed.get("created_at"), job_id)))):
            logger.error({
                "event": "inline_job_failed",
                "job_id": job_id,
                "error": str(error),
            })
        self.metadata_db.record_async_job(
            self._public_job(failed),
            payload=dict(failed.get("payload") or {}),
            include_task_tracking=bool(failed.get("include_task_tracking", True)),
        )

    def list_jobs(
            self,
            principal: AuthPrincipal,
            *,
            limit: int = 50,
            offset: int = 0,
            status: str | None = None,
            job_type: str | None = None,
            query: str | None = None,
            sort: str | None = None,
            order: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        self._backfill_metadata_if_empty(principal)
        items, total = self.metadata_db.list_async_jobs(
            is_admin=principal.is_admin,
            api_key_id=principal.key_id,
            limit=limit,
            offset=offset,
            status=status,
            job_type=job_type,
            query=query,
            sort=sort,
            order=order,
        )
        ensured_items = [self._ensure_public_job_previews(item) for item in items]
        return ensured_items, total

    def _scan_job_files(
            self,
            principal: AuthPrincipal,
            *,
            limit: int = 200,
            status: str | None = None,
            job_type: str | None = None,
    ) -> list[dict[str, object]]:
        limit_value = max(1, min(limit, 500))
        status_filter = _clean_text(status)
        type_filter = _clean_text(job_type)
        jobs: list[dict[str, object]] = []
        for path in sorted(self.jobs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            job = self._read_json(path)
            job = self._assert_job_access(job, principal)
            if job is None:
                continue
            if status_filter and _clean_text(job.get("status")) != status_filter:
                continue
            if type_filter and _clean_text(job.get("type")) != type_filter:
                continue
            jobs.append(self._ensure_public_job_previews(self._public_job(job, self._load_result(str(job.get("id") or "")))))
            if len(jobs) >= limit_value:
                break
        return jobs

    def _backfill_metadata_if_empty(self, principal: AuthPrincipal) -> None:
        if self.metadata_db.has_any_async_job_records(is_admin=principal.is_admin, api_key_id=principal.key_id):
            return
        scope_key = "*" if principal.is_admin else principal.key_id
        if scope_key in self._metadata_backfill_attempted_scopes:
            return
        self._metadata_backfill_attempted_scopes.add(scope_key)
        for public_job in self._scan_job_files(principal, limit=500):
            job = self._load_job(str(public_job.get("id") or ""))
            result = self._load_result(str(public_job.get("id") or ""))
            self.metadata_db.record_async_job(
                public_job,
                payload=dict((job or {}).get("payload") or {}),
                preview_images=list(public_job.get("preview_images") or []),
                result_path=str(self._result_file(str(public_job.get("id") or ""))) if result is not None else None,
            )

    def summarize_jobs(self, principal: AuthPrincipal) -> dict[str, int]:
        self._backfill_metadata_if_empty(principal)
        return self.metadata_db.summarize_async_jobs(is_admin=principal.is_admin, api_key_id=principal.key_id)

    def list_gallery_jobs(
            self,
            principal: AuthPrincipal,
            *,
            limit: int = 20,
            offset: int = 0,
            query: str | None = None,
            sort: str | None = None,
            order: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        self._backfill_metadata_if_empty(principal)
        items, total = self.metadata_db.list_gallery_jobs(
            is_admin=principal.is_admin,
            api_key_id=principal.key_id,
            limit=limit,
            offset=offset,
            query=query,
            sort=sort,
            order=order,
        )
        ensured_items = [self._ensure_public_job_previews(item) for item in items]
        return ensured_items, total

    def count_gallery_jobs(self, principal: AuthPrincipal) -> int:
        _, total = self.list_gallery_jobs(principal, limit=1, offset=0)
        return total

    def list_waterfall_images(
            self,
            principal: AuthPrincipal,
            *,
            limit: int = 40,
            offset: int = 0,
            query: str | None = None,
            include_blocked: bool = False,
    ) -> tuple[list[dict[str, object]], int]:
        self._backfill_metadata_if_empty(principal)
        items, total = self.metadata_db.list_waterfall_images(
            is_admin=principal.is_admin,
            api_key_id=principal.key_id,
            limit=limit,
            offset=offset,
            query=query,
            include_blocked=include_blocked,
        )
        ensured_items: list[dict[str, object]] = []
        for item in items:
            ensured = ensure_preview_image_metadata(dict(item), base_url=config.base_url or None)
            if ensured.get("wall_url"):
                ensured["src"] = ensured["wall_url"]
            ensured_items.append(ensured)
        return ensured_items, total

    def update_gallery_image_state(
            self,
            job_id: str,
            image_index: int,
            *,
            is_recommended: bool | None = None,
            is_pinned: bool | None = None,
            is_blocked: bool | None = None,
    ) -> dict[str, object] | None:
        return self.metadata_db.update_gallery_image_state(
            job_id=job_id,
            image_index=image_index,
            is_recommended=is_recommended,
            is_pinned=is_pinned,
            is_blocked=is_blocked,
        )

    def list_image_conversations(self, principal: AuthPrincipal) -> list[dict[str, object]]:
        return self.metadata_db.list_image_conversations(api_key_id=principal.key_id)

    def save_image_conversation(
            self,
            conversation: dict[str, object],
            principal: AuthPrincipal,
    ) -> dict[str, object]:
        return self.metadata_db.upsert_image_conversation(
            conversation,
            api_key_id=principal.key_id,
            api_key_name=principal.name,
        )

    def replace_image_conversations(
            self,
            conversations: list[dict[str, object]],
            principal: AuthPrincipal,
    ) -> list[dict[str, object]]:
        return self.metadata_db.replace_image_conversations(
            conversations,
            api_key_id=principal.key_id,
            api_key_name=principal.name,
        )

    def delete_image_conversation(self, conversation_id: str, principal: AuthPrincipal) -> bool:
        return self.metadata_db.delete_image_conversation(conversation_id, api_key_id=principal.key_id)

    def clear_image_conversations(self, principal: AuthPrincipal) -> None:
        self.metadata_db.clear_image_conversations(api_key_id=principal.key_id)

    def get_job(self, job_id: str, principal: AuthPrincipal) -> dict[str, object] | None:
        job = self._assert_job_access(self._load_job(job_id), principal)
        if job is None:
            return None
        return self._public_job(job, self._load_result(job_id))

    def get_job_result(self, job_id: str, principal: AuthPrincipal) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        job = self._assert_job_access(self._load_job(job_id), principal)
        if job is None:
            return None, None
        result = self._load_result(job_id)
        return self._public_job(job, result), result

    def get_job_log(self, job_id: str, principal: AuthPrincipal) -> tuple[dict[str, object] | None, str]:
        job = self._assert_job_access(self._load_job(job_id), principal)
        if job is None:
            return None, ""
        result = self._load_result(job_id)
        public_job = self._public_job(job, result)
        log_path = Path(str(job.get("log_path") or ""))
        if not log_path.is_file():
            return public_job, ""
        try:
            return public_job, log_path.read_text(encoding="utf-8")
        except OSError:
            return public_job, ""

    def _execute_job(self, job: dict[str, object]) -> dict[str, object]:
        payload = dict(job.get("payload") or {})
        job_type = str(job.get("type") or "")
        if job_type == "chat.completions":
            return self.chatgpt_service.create_chat_completion(payload)
        if job_type == "responses":
            return self.chatgpt_service.create_response(payload)
        if job_type == "images.generations":
            prompt = _clean_text(payload.get("prompt"))
            if not prompt:
                raise ValueError("prompt is required")
            response_format = _clean_text(payload.get("response_format")) or None
            base_url = config.base_url or None
            return self._execute_streaming_image_job(
                job,
                self.chatgpt_service.stream_image_generation(
                    prompt,
                    _clean_text(payload.get("model")) or "gpt-image-2",
                    max(1, int(payload.get("n") or 1)),
                    normalize_image_size(payload.get("size")),
                    response_format,
                    base_url,
                    quality=normalize_image_quality(payload.get("quality")),
                    request_id=str(job.get("id") or "") or None,
                ),
                fallback_error="image generation failed",
            )
        if job_type == "images.edits":
            prompt = _clean_text(payload.get("prompt"))
            if not prompt:
                raise ValueError("prompt is required")
            images = _decode_async_image_payload(payload.get("images") or payload.get("image"))
            if not images:
                raise ValueError("images is required")
            response_format = _clean_text(payload.get("response_format")) or None
            base_url = config.base_url or None
            return self._execute_streaming_image_job(
                job,
                self.chatgpt_service.stream_image_edit(
                    prompt,
                    images,
                    _clean_text(payload.get("model")) or "gpt-image-2",
                    max(1, int(payload.get("n") or 1)),
                    _clean_text(payload.get("size")) or None,
                    response_format,
                    base_url,
                    request_id=str(job.get("id") or "") or None,
                ),
                fallback_error="image edit failed",
            )
        raise ValueError(f"unsupported async job type: {job_type}")

    def _execute_streaming_image_job(
            self,
            job: dict[str, object],
            chunks,
            *,
            fallback_error: str,
    ) -> dict[str, object]:
        created = None
        image_items: list[dict[str, object]] = []
        chunk_iterator = iter(chunks)
        while True:
            try:
                chunk = next(chunk_iterator)
            except StopIteration:
                break
            except Exception as exc:
                if image_items:
                    logger.warning({
                        "event": "async_image_job_partial_success_after_error",
                        "job_id": job.get("id"),
                        "result_count": len(image_items),
                        "error": str(exc),
                    })
                    break
                raise
            if not isinstance(chunk, dict):
                continue
            data = chunk.get("data")
            if not isinstance(data, list) or not data:
                continue
            next_items = [item for item in data if isinstance(item, dict)]
            if not next_items:
                continue
            if created is None:
                created = chunk.get("created")
            self._store_partial_image_result(job, chunk)
            image_items.extend(next_items)
        if not image_items:
            raise ValueError(fallback_error)
        return {"created": created, "data": image_items}

    def _run_job(self, job_id: str) -> None:
        running = self._update_job(job_id, status="running", error=None)
        if running is None:
            return
        log_path = Path(str(running.get("log_path") or self._task_log_file(running.get("created_at"), job_id)))
        self.metadata_db.record_task_log(job_id, str(log_path))
        self.metadata_db.record_async_job(self._public_job(running), payload=dict(running.get("payload") or {}))
        with logger.task_context(log_path):
            logger.info({
                "event": "async_job_started",
                "job_id": job_id,
                "job_type": running.get("type"),
                "model": running.get("model"),
                "log_path": str(log_path),
            })
            try:
                result = self._execute_job(running)
                result_payload = {"result": result}
                result_file = self._result_file(job_id)
                self._write_json(result_file, result_payload)
                succeeded = self._update_job(job_id, status="succeeded", error=None)
                logger.info({
                    "event": "async_job_succeeded",
                    "job_id": job_id,
                    "result_count": _count_result_items(result_payload),
                })
                if succeeded is not None:
                    self.metadata_db.record_async_job(
                        self._public_job(succeeded, result_payload),
                        payload=dict(succeeded.get("payload") or {}),
                        preview_images=_extract_preview_images(result_payload),
                        result_path=str(result_file),
                    )
            except Exception as exc:
                failed = self._update_job(
                    job_id,
                    status="failed",
                    error=_error_payload(exc, default_status_code=502),
                )
                logger.error({
                    "event": "async_job_failed",
                    "job_id": job_id,
                    "error": str(exc),
                })
                if failed is not None:
                    self.metadata_db.record_async_job(
                        self._public_job(failed),
                        payload=dict(failed.get("payload") or {}),
                    )
