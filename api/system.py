from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from api.support import require_auth_key, require_session_principal
from services.api_key_service import api_key_service
from services.config import config
from services.data_service import (
    data_maintenance_service,
    guess_media_type,
    list_recent_image_files,
    read_system_log_tail,
    resolve_image_path,
)
from services.history_recovery_service import history_recovery_service
from services.proxy_service import test_proxy


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProxyTestRequest(BaseModel):
    url: str = ""


def _settings_response() -> dict[str, object]:
    return {
        "config": config.get(),
        "effective_config": config.get_effective(),
        "env_overrides": config.env_overrides(),
    }


def create_router(app_version: str) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/login")
    async def login(authorization: str | None = Header(default=None)):
        principal = require_session_principal(authorization)
        return {
            "ok": True,
            "version": app_version,
            "session": api_key_service.session_payload(principal),
        }

    @router.get("/auth/session")
    async def get_session(authorization: str | None = Header(default=None)):
        principal = require_session_principal(authorization)
        return {
            "version": app_version,
            "session": api_key_service.session_payload(principal),
        }

    @router.get("/version")
    async def get_version():
        return {"version": app_version}

    @router.get("/api/settings")
    async def get_settings(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return _settings_response()

    @router.post("/api/settings")
    async def save_settings(body: SettingsUpdateRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        config.update(body.model_dump(mode="python"))
        return _settings_response()

    @router.get("/api/data/stats")
    async def get_data_stats(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"stats": await run_in_threadpool(data_maintenance_service.collect_stats)}

    @router.post("/api/data/cleanup")
    async def cleanup_data(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"result": await run_in_threadpool(data_maintenance_service.cleanup, force=True)}

    @router.get("/api/logs/system")
    async def get_system_log_tail(authorization: str | None = Header(default=None), lines: int = 200):
        require_auth_key(authorization)
        return {"log": await run_in_threadpool(read_system_log_tail, lines)}

    @router.get("/api/images/management")
    async def get_image_management(authorization: str | None = Header(default=None), limit: int = 24):
        require_auth_key(authorization)
        return {"images": await run_in_threadpool(list_recent_image_files, limit)}

    @router.post("/api/system/recovery/scan")
    async def scan_history_recovery(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"report": await run_in_threadpool(history_recovery_service.scan_report)}

    @router.post("/api/system/recovery/apply")
    async def apply_history_recovery(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"result": await run_in_threadpool(history_recovery_service.apply)}

    @router.post("/api/proxy/test")
    async def test_proxy_endpoint(body: ProxyTestRequest, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        candidate = (body.url or "").strip() or config.get_proxy_settings()
        if not candidate:
            raise HTTPException(status_code=400, detail={"error": "proxy url is required"})
        return {"result": await run_in_threadpool(test_proxy, candidate)}

    @router.get("/api/view/data/{date_segment}/{file_name}")
    @router.get("/api/images/{date_segment}/{file_name}")
    async def get_image(date_segment: str, file_name: str):
        path = resolve_image_path(date_segment, file_name)
        return FileResponse(path, media_type=guess_media_type(path), filename=path.name, content_disposition_type="inline")

    return router

