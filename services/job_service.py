from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from services.api_key_service import AuthPrincipal
from services.chatgpt_service import ChatGPTService
from services.config import config


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


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
            max_workers: int = 4,
    ):
        self.jobs_dir = jobs_dir
        self.job_results_dir = job_results_dir
        self.chatgpt_service = chatgpt_service
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.job_results_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="async-job")

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _result_file(self, job_id: str) -> Path:
        return self.job_results_dir / f"{job_id}.json"

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
    def _public_job(job: dict[str, object]) -> dict[str, object]:
        return {
            "id": job.get("id"),
            "type": job.get("type"),
            "status": job.get("status"),
            "model": job.get("model"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "api_key_id": job.get("api_key_id"),
            "error": job.get("error"),
        }

    def _load_job(self, job_id: str) -> dict[str, object] | None:
        return self._read_json(self._job_file(job_id))

    def _load_result(self, job_id: str) -> dict[str, object] | None:
        return self._read_json(self._result_file(job_id))

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
            "api_key_id": principal.key_id,
            "api_key_name": principal.name,
            "payload": dict(payload or {}),
            "error": None,
        }
        with self._lock:
            self._store_job(job)
        self._executor.submit(self._run_job, str(job["id"]))
        return self._public_job(job)

    def list_jobs(self, principal: AuthPrincipal, *, limit: int = 50) -> list[dict[str, object]]:
        limit_value = max(1, min(limit, 200))
        jobs: list[dict[str, object]] = []
        for path in sorted(self.jobs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            job = self._read_json(path)
            job = self._assert_job_access(job, principal)
            if job is None:
                continue
            jobs.append(self._public_job(job))
            if len(jobs) >= limit_value:
                break
        return jobs

    def get_job(self, job_id: str, principal: AuthPrincipal) -> dict[str, object] | None:
        job = self._assert_job_access(self._load_job(job_id), principal)
        if job is None:
            return None
        return self._public_job(job)

    def get_job_result(self, job_id: str, principal: AuthPrincipal) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        job = self._assert_job_access(self._load_job(job_id), principal)
        if job is None:
            return None, None
        return self._public_job(job), self._load_result(job_id)

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
            response_format = _clean_text(payload.get("response_format")) or "b64_json"
            base_url = config.base_url or None
            if response_format == "url" and not base_url:
                raise ValueError("base_url is required for async image url responses")
            return self.chatgpt_service.generate_with_pool(
                prompt,
                _clean_text(payload.get("model")) or "gpt-image-2",
                max(1, int(payload.get("n") or 1)),
                _clean_text(payload.get("size")) or None,
                response_format,
                base_url,
            )
        if job_type == "images.edits":
            prompt = _clean_text(payload.get("prompt"))
            if not prompt:
                raise ValueError("prompt is required")
            images = _decode_async_image_payload(payload.get("images") or payload.get("image"))
            if not images:
                raise ValueError("images is required")
            response_format = _clean_text(payload.get("response_format")) or "b64_json"
            base_url = config.base_url or None
            if response_format == "url" and not base_url:
                raise ValueError("base_url is required for async image url responses")
            return self.chatgpt_service.edit_with_pool(
                prompt,
                images,
                _clean_text(payload.get("model")) or "gpt-image-2",
                max(1, int(payload.get("n") or 1)),
                _clean_text(payload.get("size")) or None,
                response_format,
                base_url,
            )
        raise ValueError(f"unsupported async job type: {job_type}")

    def _run_job(self, job_id: str) -> None:
        running = self._update_job(job_id, status="running", error=None)
        if running is None:
            return
        try:
            result = self._execute_job(running)
            self._write_json(self._result_file(job_id), {"result": result})
            self._update_job(job_id, status="succeeded", error=None)
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                error={"message": str(exc)},
            )
