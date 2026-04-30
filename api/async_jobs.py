from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.support import ensure_model_access, require_client_principal, reserve_image_quota
from services.job_service import JobService


class AsyncJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class GalleryImageStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_recommended: bool | None = None
    is_pinned: bool | None = None
    is_blocked: bool | None = None


class ImageConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation: dict[str, Any]


class ImageConversationListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[dict[str, Any]] = Field(default_factory=list)


def _sse_line(event: str, payload: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _coerce_positive_int(value: object, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _job_error_payload(job_id: str, job: dict[str, object] | None, message: str = "job failed") -> dict[str, object]:
    error = job.get("error") if isinstance(job, dict) else None
    error = error if isinstance(error, dict) else {}
    error_message = str(error.get("message") or message)
    status_code = int(error.get("status_code") or 500)
    code = str(error.get("code") or "job_failed")
    return {
        "job_id": job_id,
        "job": job,
        "error": {
            "message": error_message,
            "code": code,
            "status_code": status_code,
        },
        "message": error_message,
        "code": code,
        "status_code": status_code,
    }


def create_router(job_service: JobService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/async/jobs")
    async def create_job(body: AsyncJobCreateRequest, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        model = body.payload.get("model") if isinstance(body.payload, dict) else None
        if not model:
            model = "gpt-image-2" if str(body.type).startswith("images.") else "auto"
        ensure_model_access(principal, model)
        if str(body.type).startswith("images."):
            principal = reserve_image_quota(principal, _coerce_positive_int(body.payload.get("n"), 1))
        job = job_service.submit_job(body.type, body.payload, principal)
        return {"job": job}

    @router.get("/api/async/jobs")
    async def list_jobs(
            authorization: str | None = Header(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
            status: str | None = Query(default=None),
            job_type: str | None = Query(default=None, alias="type"),
            query: str | None = Query(default=None),
            sort: str | None = Query(default="created_at"),
            order: str | None = Query(default="desc"),
            include_hidden: bool = Query(default=False),
    ):
        principal = require_client_principal(authorization)
        items, total = job_service.list_jobs(
            principal,
            limit=limit,
            offset=offset,
            status=status,
            job_type=job_type,
            query=query,
            sort=sort,
            order=order,
            include_hidden=include_hidden,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "summary": job_service.summarize_jobs(principal, include_hidden=include_hidden),
        }

    @router.get("/api/gallery")
    async def list_gallery(
            authorization: str | None = Header(default=None),
            limit: int = Query(default=20, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
            query: str | None = Query(default=None),
            sort: str | None = Query(default="created_at"),
            order: str | None = Query(default="desc"),
            include_hidden: bool = Query(default=False),
    ):
        principal = require_client_principal(authorization)
        items, total = job_service.list_gallery_jobs(
            principal,
            limit=limit,
            offset=offset,
            query=query,
            sort=sort,
            order=order,
            include_hidden=include_hidden,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @router.get("/api/gallery/wall")
    async def list_gallery_wall(
            authorization: str | None = Header(default=None),
            limit: int = Query(default=40, ge=1, le=100),
            offset: int = Query(default=0, ge=0),
            query: str | None = Query(default=None),
            include_blocked: bool = Query(default=False),
            sort: str | None = Query(default="created_at"),
            order: str | None = Query(default="desc"),
            include_hidden: bool = Query(default=False),
    ):
        principal = require_client_principal(authorization)
        items, total = job_service.list_waterfall_images(
            principal,
            limit=limit,
            offset=offset,
            query=query,
            include_blocked=include_blocked,
            sort=sort,
            order=order,
            include_hidden=include_hidden,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @router.post("/api/gallery/images/{job_id}/{image_index}")
    async def update_gallery_image_state(
            job_id: str,
            image_index: int,
            body: GalleryImageStateRequest,
            authorization: str | None = Header(default=None),
    ):
        principal = require_client_principal(authorization)
        if not principal.is_admin:
            raise HTTPException(status_code=403, detail={"error": "admin key required"})
        item = job_service.update_gallery_image_state(
            job_id,
            image_index,
            is_recommended=body.is_recommended,
            is_pinned=body.is_pinned,
            is_blocked=body.is_blocked,
        )
        if item is None:
            raise HTTPException(status_code=404, detail={"error": "image not found"})
        return {"item": item}

    @router.get("/api/image/conversations")
    async def list_image_conversations(authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        return {"items": job_service.list_image_conversations(principal)}

    @router.put("/api/image/conversations")
    async def replace_image_conversations(
            body: ImageConversationListRequest,
            authorization: str | None = Header(default=None),
    ):
        principal = require_client_principal(authorization)
        items = job_service.replace_image_conversations(body.items, principal)
        return {"items": items}

    @router.put("/api/image/conversations/{conversation_id}")
    async def save_image_conversation(
            conversation_id: str,
            body: ImageConversationRequest,
            authorization: str | None = Header(default=None),
    ):
        principal = require_client_principal(authorization)
        body_conversation_id = str(body.conversation.get("id") or "").strip()
        if not body_conversation_id:
            body.conversation["id"] = conversation_id
        elif body_conversation_id != conversation_id:
            raise HTTPException(status_code=400, detail={"error": "conversation id mismatch"})
        item = job_service.save_image_conversation(body.conversation, principal)
        return {"item": item}

    @router.delete("/api/image/conversations/{conversation_id}")
    async def delete_image_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        deleted = job_service.delete_image_conversation(conversation_id, principal)
        return {"deleted": deleted}

    @router.delete("/api/image/conversations")
    async def clear_image_conversations(authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        job_service.clear_image_conversations(principal)
        return {"deleted": True}

    @router.get("/api/async/jobs/{job_id}")
    async def get_job(job_id: str, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        job = job_service.get_job(job_id, principal)
        if job is None:
            raise HTTPException(status_code=404, detail={"error": "job not found"})
        return {"job": job}

    @router.get("/api/async/jobs/{job_id}/result")
    async def get_job_result(job_id: str, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        job, result = job_service.get_job_result(job_id, principal)
        if job is None:
            raise HTTPException(status_code=404, detail={"error": "job not found"})
        if job.get("status") == "succeeded":
            return {"job": job, "result": result.get("result") if isinstance(result, dict) else None}
        if job.get("status") == "failed":
            raise HTTPException(status_code=409, detail={"job": job})
        raise HTTPException(status_code=202, detail={"job": job})

    @router.get("/api/async/jobs/{job_id}/log")
    async def get_job_log(job_id: str, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        job, log_text = job_service.get_job_log(job_id, principal)
        if job is None:
            raise HTTPException(status_code=404, detail={"error": "job not found"})
        return {
            "job": job,
            "log_path": job.get("log_path"),
            "log_text": log_text,
        }

    @router.get("/api/async/jobs/{job_id}/events")
    async def stream_job_events(
            job_id: str,
            authorization: str | None = Header(default=None),
            ping_interval: float = Query(default=10.0, ge=1.0, le=30.0),
    ):
        principal = require_client_principal(authorization)
        initial = job_service.get_job(job_id, principal)
        if initial is None:
            raise HTTPException(status_code=404, detail={"error": "job not found"})

        def event_stream():
            last_status = ""
            last_result_count = 0
            while True:
                job, result = job_service.get_job_result(job_id, principal)
                if job is None:
                    yield _sse_line(
                        "error",
                        {
                            "job_id": job_id,
                            "error": {"message": "job not found", "code": "job_not_found", "status_code": 404},
                            "message": "job not found",
                            "code": "job_not_found",
                            "status_code": 404,
                        },
                    )
                    return
                status = str(job.get("status") or "")
                if status != last_status:
                    yield _sse_line("status", {"job": job})
                    last_status = status
                result_count = int(job.get("result_count") or 0)
                if status in {"queued", "running"} and result_count > last_result_count and isinstance(result, dict):
                    yield _sse_line(
                        "partial_result",
                        {"job": job, "result": result.get("result"), "result_count": result_count},
                    )
                    last_result_count = result_count
                yield _sse_line("ping", {"job_id": job_id, "status": status, "ts": int(time.time())})
                if status == "succeeded":
                    yield _sse_line("result", {"job": job, "result": result.get("result") if isinstance(result, dict) else None})
                    yield b"data: [DONE]\n\n"
                    return
                if status == "failed":
                    yield _sse_line("error", _job_error_payload(job_id, job))
                    yield b"data: [DONE]\n\n"
                    return
                time.sleep(ping_interval)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router
