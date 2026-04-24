from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.support import require_client_principal
from services.chatgpt_service import ChatGPTService
from services.model_registry import model_registry


def create_router(chatgpt_service: ChatGPTService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/catalog/models")
    async def list_catalog_models(authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        try:
            result = await run_in_threadpool(chatgpt_service.list_models)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        items = result.get("data") if isinstance(result.get("data"), list) else []
        if not principal.is_admin and principal.allowed_models:
            items = [
                item for item in items
                if isinstance(item, dict) and str(item.get("id") or "").strip() in principal.allowed_models
            ]
        return {
            "items": model_registry.build_catalog(items),
            "openai_models_endpoint": "/v1/models",
        }

    return router
