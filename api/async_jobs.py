from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.support import ensure_model_access, require_client_principal
from services.job_service import JobService


class AsyncJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _sse_line(event: str, payload: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def create_router(job_service: JobService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/async/jobs")
    async def create_job(body: AsyncJobCreateRequest, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        model = body.payload.get("model") if isinstance(body.payload, dict) else None
        if not model:
            model = "gpt-image-2" if str(body.type).startswith("images.") else "auto"
        ensure_model_access(principal, model)
        job = job_service.submit_job(body.type, body.payload, principal)
        return {"job": job}

    @router.get("/api/async/jobs")
    async def list_jobs(
            authorization: str | None = Header(default=None),
            limit: int = Query(default=50, ge=1, le=200),
            status: str | None = Query(default=None),
            job_type: str | None = Query(default=None, alias="type"),
    ):
        principal = require_client_principal(authorization)
        return {
            "items": job_service.list_jobs(principal, limit=limit, status=status, job_type=job_type),
            "summary": job_service.summarize_jobs(principal),
        }

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
            while True:
                job, result = job_service.get_job_result(job_id, principal)
                if job is None:
                    yield _sse_line("error", {"job_id": job_id, "error": "job not found"})
                    return
                status = str(job.get("status") or "")
                if status != last_status:
                    yield _sse_line("status", {"job": job})
                    last_status = status
                if status == "succeeded":
                    yield _sse_line("result", {"job": job, "result": result.get("result") if isinstance(result, dict) else None})
                    yield b"data: [DONE]\n\n"
                    return
                if status == "failed":
                    yield _sse_line("error", {"job": job})
                    yield b"data: [DONE]\n\n"
                    return
                yield _sse_line("ping", {"job_id": job_id, "status": status, "ts": int(time.time())})
                time.sleep(ping_interval)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router
