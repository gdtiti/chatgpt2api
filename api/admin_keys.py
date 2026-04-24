from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.support import require_admin_key
from services.api_key_service import APIKeyService
from services.config import config


class APIKeyCreateRequest(BaseModel):
    name: str = ""
    allowed_models: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["inference"])
    expires_at: str | None = None


class APIKeyUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    allowed_models: list[str] | None = None
    scopes: list[str] | None = None
    expires_at: str | None = None


def create_router(api_key_service: APIKeyService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/keys")
    async def list_keys(authorization: str | None = Header(default=None)):
        require_admin_key(authorization)
        return {"items": api_key_service.list_keys()}

    @router.post("/api/admin/keys")
    async def create_key(body: APIKeyCreateRequest, authorization: str | None = Header(default=None)):
        require_admin_key(authorization)
        created = api_key_service.create_key(
            name=body.name,
            allowed_models=body.allowed_models,
            scopes=body.scopes,
            expires_at=body.expires_at,
        )
        return created

    @router.post("/api/admin/keys/{key_id}")
    async def update_key(key_id: str, body: APIKeyUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin_key(authorization)
        item = api_key_service.update_key(
            key_id,
            name=body.name,
            enabled=body.enabled,
            allowed_models=body.allowed_models,
            scopes=body.scopes,
            expires_at=body.expires_at,
        )
        if item is None:
            raise HTTPException(status_code=404, detail={"error": "api key not found"})
        return {"item": item}

    @router.post("/api/admin/keys/{key_id}/rotate")
    async def rotate_key(key_id: str, authorization: str | None = Header(default=None)):
        require_admin_key(authorization)
        rotated = api_key_service.rotate_key(key_id)
        if rotated is None:
            raise HTTPException(status_code=404, detail={"error": "api key not found"})
        return rotated

    @router.delete("/api/admin/keys/{key_id}")
    async def delete_key(key_id: str, authorization: str | None = Header(default=None)):
        require_admin_key(authorization)
        if not api_key_service.delete_key(key_id):
            raise HTTPException(status_code=404, detail={"error": "api key not found"})
        return {"ok": True}

    @router.post("/api/admin/image-placeholder")
    async def upload_placeholder(
            image: UploadFile = File(...),
            authorization: str | None = Header(default=None),
    ):
        require_admin_key(authorization)
        payload = await image.read()
        if not payload:
            raise HTTPException(status_code=400, detail={"error": "image file is empty"})
        suffix = Path(image.filename or "placeholder.png").suffix or ".png"
        target = config.image_placeholder_dir / f"image-placeholder{suffix.lower()}"
        target.write_bytes(payload)
        relative_path = target.relative_to(config.path.parent).as_posix()
        updated = config.update({"image_placeholder_path": relative_path})
        return {
            "placeholder_path": relative_path,
            "config": updated,
        }

    return router
