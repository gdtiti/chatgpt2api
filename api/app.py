from __future__ import annotations

from contextlib import asynccontextmanager
from threading import Event

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import accounts, admin_keys, ai, async_jobs, catalog, system
from api.support import resolve_web_asset, start_limited_account_watcher
from services.account_service import account_service
from services.api_key_service import api_key_service
from services.chatgpt_service import ChatGPTService
from services.config import config
from services.job_service import JobService


def create_app(
        *,
        chatgpt_service: ChatGPTService | None = None,
        job_service: JobService | None = None,
) -> FastAPI:
    chatgpt_service = chatgpt_service or ChatGPTService(account_service)
    job_service = job_service or JobService(config.jobs_dir, config.job_results_dir, chatgpt_service)
    app_version = config.app_version

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = Event()
        thread = start_limited_account_watcher(stop_event)
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)
            job_service.shutdown(wait=False)

    app = FastAPI(title="chatgpt2api", version=app_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ai.create_router(chatgpt_service))
    app.include_router(catalog.create_router(chatgpt_service))
    app.include_router(async_jobs.create_router(job_service))
    app.include_router(admin_keys.create_router(api_key_service))
    app.include_router(accounts.create_router())
    app.include_router(system.create_router(app_version))
    if config.images_dir.exists():
        app.mount("/images", StaticFiles(directory=str(config.images_dir)), name="images")

    @app.get("/{full_path:path}", include_in_schema=False)
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
