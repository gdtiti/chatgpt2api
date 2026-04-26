from __future__ import annotations

from contextlib import asynccontextmanager
import json
from time import perf_counter
from threading import Event
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import accounts, admin_keys, ai, async_jobs, catalog, system
from api.support import extract_bearer_token, resolve_web_asset, start_limited_account_watcher
from services.account_service import account_service
from services.api_key_service import api_key_service
from services.chatgpt_service import ChatGPTService
from services.config import config
from services.data_service import data_maintenance_service
from services.job_service import JobService
from services.metadata_db import metadata_db
from utils.log import DEFAULT_SYSTEM_LOG_FILE, logger


def _build_request_payload_hint(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        input_value = payload.get("input")
        if isinstance(input_value, str):
            prompt = input_value.strip()
    if not prompt:
        messages = payload.get("messages")
        if isinstance(messages, list):
            for item in reversed(messages):
                if isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, str) and content.strip():
                        prompt = content.strip()
                        break
    parts: list[str] = []
    if prompt:
        normalized_prompt = " ".join(prompt.split())
        if len(normalized_prompt) > 120:
            normalized_prompt = normalized_prompt[:120].rstrip() + "..."
        parts.append(normalized_prompt)
    model = str(payload.get("model") or "").strip()
    if model:
        parts.append(f"model={model}")
    size = str(payload.get("size") or "").strip()
    if size:
        parts.append(f"size={size}")
    count = payload.get("n")
    if count is not None:
        parts.append(f"n={count}")
    return " | ".join(parts) if parts else None


def create_app(
        *,
        chatgpt_service: ChatGPTService | None = None,
        job_service: JobService | None = None,
) -> FastAPI:
    chatgpt_service = chatgpt_service or ChatGPTService(account_service)
    job_service = job_service or JobService(
        config.jobs_dir,
        config.job_results_dir,
        chatgpt_service,
        task_logs_dir=config.task_logs_dir,
    )
    app_version = config.app_version

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = Event()
        thread = start_limited_account_watcher(stop_event)

        def data_worker() -> None:
            while not stop_event.is_set():
                try:
                    data_maintenance_service.run_if_due()
                except Exception as exc:
                    print(f"[data-cleanup-watcher] fail {exc}")
                stop_event.wait(max(30, config.data_cleanup_interval_minutes * 60))

        data_thread = Thread(target=data_worker, name="data-cleanup-watcher", daemon=True)
        data_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)
            data_thread.join(timeout=1)
            job_service.shutdown(wait=False)

    app = FastAPI(
        title="chatgpt2api",
        version=app_version,
        lifespan=lifespan,
        docs_url="/swagger",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if logger.system_log_path == DEFAULT_SYSTEM_LOG_FILE:
        logger.set_system_log_path(config.system_log_file)
    try:
        metadata_db.record_settings(config.get())
        metadata_db.record_accounts(account_service.list_accounts())
    except Exception:
        pass

    @app.middleware("http")
    async def persist_request_metadata(request, call_next):
        started_at = perf_counter()
        principal = api_key_service.peek_principal(
            extract_bearer_token(request.headers.get("authorization")),
            allow_admin=True,
            strict=False,
        )
        model: str | None = None
        request_id = request.headers.get("x-request-id") or None
        payload_hint: str | None = None
        content_type = str(request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            try:
                body = await request.body()
                if body:
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict):
                        candidate_model = str(payload.get("model") or "").strip()
                        model = candidate_model or None
                        payload_hint = _build_request_payload_hint(payload)
                        if not request_id:
                            header_request_id = str(payload.get("request_id") or "").strip()
                            request_id = header_request_id or None
            except Exception:
                payload_hint = None

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            try:
                metadata_db.record_request_log(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    api_key_id=principal.key_id if principal else None,
                    api_key_name=principal.name if principal else None,
                    model=model,
                    request_id=request_id,
                    payload_hint=payload_hint,
                )
            except Exception:
                pass

    app.include_router(ai.create_router(chatgpt_service, job_service))
    app.include_router(catalog.create_router(chatgpt_service))
    app.include_router(async_jobs.create_router(job_service))
    app.include_router(admin_keys.create_router(api_key_service))
    app.include_router(accounts.create_router())
    app.include_router(system.create_router(app_version))
    if config.images_dir.exists():
        app.mount("/images", StaticFiles(directory=str(config.images_dir)), name="images")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_web(full_path: str):
        asset = resolve_web_asset(full_path)
        if asset is not None:
            return FileResponse(asset)
        if full_path.strip("/").startswith("_next/"):
            raise HTTPException(status_code=404, detail="Not Found")
        fallback = resolve_web_asset("")
        if fallback is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(fallback)

    return app
