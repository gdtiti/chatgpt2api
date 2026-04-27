from __future__ import annotations

import time
from collections.abc import Iterator
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.support import (
    ensure_model_access,
    raise_image_quota_error,
    require_client_principal,
    reserve_image_quota,
    resolve_image_base_url,
)
from services.account_service import account_service
from services.chatgpt_service import ChatGPTService, ImageGenerationError
from services.config import config
from services.image_options import ImageOptionError, normalize_image_quality, normalize_image_size
from services.job_service import JobService
from utils.helper import (
    has_response_image_generation_tool,
    is_image_chat_request,
    responses_sse_stream,
    sse_json_stream,
)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    size: str | None = None
    quality: str | None = None
    response_format: str | None = None
    history_disabled: bool = True
    stream: bool | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    prompt: str | None = None
    n: int | None = None
    stream: bool | None = None
    modalities: list[str] | None = None
    messages: list[dict[str, object]] | None = None


class ResponseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    input: object | None = None
    tools: list[dict[str, object]] | None = None
    tool_choice: object | None = None
    stream: bool | None = None


def _tracked_image_stream(
        *,
        chunks: Iterator[dict[str, object]],
        job_service: JobService,
        job_id: str,
        include_gallery: bool,
        include_waterfall: bool,
) -> Iterator[dict[str, object]]:
    created: int | None = None
    image_items: list[dict[str, object]] = []
    try:
        for chunk in chunks:
            next_chunk = dict(chunk)
            next_chunk["job_id"] = job_id
            if created is None:
                try:
                    created = int(next_chunk.get("created") or time.time())
                except (TypeError, ValueError):
                    created = int(time.time())
            data = next_chunk.get("data")
            if isinstance(data, list):
                image_items.extend(item for item in data if isinstance(item, dict))
            yield next_chunk
        job_service.finish_inline_job(
            job_id,
            {"created": created or int(time.time()), "data": image_items},
            include_gallery=include_gallery,
            include_waterfall=include_waterfall,
        )
    except Exception as exc:
        job_service.fail_inline_job(job_id, exc)
        raise


def _openai_compat_image_tracking_options() -> dict[str, bool]:
    include_task_tracking = config.openai_compat_image_task_tracking_enabled
    include_gallery = config.openai_compat_image_gallery_enabled
    include_waterfall = config.openai_compat_image_waterfall_enabled
    return {
        "enabled": include_task_tracking or include_gallery or include_waterfall,
        "include_task_tracking": include_task_tracking,
        "include_gallery": include_gallery,
        "include_waterfall": include_waterfall,
    }


async def _run_tracked_compatible_job(
        *,
        job_type: str,
        payload: dict[str, object],
        principal,
        job_service: JobService | None,
        operation,
):
    tracking_options = _openai_compat_image_tracking_options()
    tracked_job: dict[str, object] | None = None
    if job_service is not None and tracking_options["enabled"]:
        tracked_job = job_service.start_inline_job(
            job_type,
            payload,
            principal,
            include_task_tracking=tracking_options["include_task_tracking"],
        )
    try:
        result = await run_in_threadpool(operation)
        if job_service is not None and tracked_job is not None:
            job_service.finish_inline_job(
                str(tracked_job.get("id") or ""),
                result,
                include_gallery=tracking_options["include_gallery"],
                include_waterfall=tracking_options["include_waterfall"],
            )
        return result
    except Exception as exc:
        if job_service is not None and tracked_job is not None:
            job_service.fail_inline_job(str(tracked_job.get("id") or ""), exc)
        raise


def create_router(chatgpt_service: ChatGPTService, job_service: JobService | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/models")
    async def list_models(authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        try:
            result = await run_in_threadpool(chatgpt_service.list_models)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        if principal.is_admin or not principal.allowed_models:
            return result
        data = result.get("data")
        if isinstance(data, list):
            result["data"] = [
                item for item in data
                if isinstance(item, dict) and str(item.get("id") or "").strip() in principal.allowed_models
            ]
        return result

    @router.post("/v1/images/generations")
    async def generate_images(
            body: ImageGenerationRequest,
            request: Request,
            authorization: str | None = Header(default=None),
    ):
        principal = require_client_principal(authorization)
        ensure_model_access(principal, body.model)
        try:
            size = normalize_image_size(body.size)
            quality = normalize_image_quality(body.quality)
        except ImageOptionError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        reserve_image_quota(principal, body.n)
        base_url = resolve_image_base_url(request)
        request_id = uuid4().hex
        tracking_options = _openai_compat_image_tracking_options()
        if body.stream:
            try:
                await run_in_threadpool(account_service.get_available_access_token)
            except RuntimeError as exc:
                raise_image_quota_error(exc)
            chunks = chatgpt_service.stream_image_generation(
                body.prompt, body.model, body.n, size, body.response_format, base_url, quality=quality
            )
            if job_service is not None and tracking_options["enabled"]:
                tracked_job = job_service.start_inline_job(
                    "images.generations",
                    {
                        "model": body.model,
                        "prompt": body.prompt,
                        "n": body.n,
                        "size": size,
                        "quality": quality,
                        "response_format": body.response_format,
                        "stream": True,
                    },
                    principal,
                    include_task_tracking=tracking_options["include_task_tracking"],
                )
                chunks = _tracked_image_stream(
                    chunks=chunks,
                    job_service=job_service,
                    job_id=str(tracked_job.get("id") or ""),
                    include_gallery=tracking_options["include_gallery"],
                    include_waterfall=tracking_options["include_waterfall"],
                )
            return StreamingResponse(
                sse_json_stream(chunks),
                media_type="text/event-stream",
            )
        tracked_job: dict[str, object] | None = None
        if job_service is not None and tracking_options["enabled"]:
            tracked_job = job_service.start_inline_job(
                "images.generations",
                {
                    "model": body.model,
                    "prompt": body.prompt,
                    "n": body.n,
                    "size": size,
                    "quality": quality,
                    "response_format": body.response_format,
                    "stream": False,
                },
                principal,
                include_task_tracking=tracking_options["include_task_tracking"],
            )
            request_id = str(tracked_job.get("id") or "") or request_id
        try:
            result = await run_in_threadpool(
                chatgpt_service.generate_with_pool,
                body.prompt,
                body.model,
                body.n,
                size,
                body.response_format,
                base_url,
                request_id,
                quality=quality,
            )
            if job_service is not None and tracked_job is not None:
                job_service.finish_inline_job(
                    str(tracked_job.get("id") or ""),
                    result,
                    include_gallery=tracking_options["include_gallery"],
                    include_waterfall=tracking_options["include_waterfall"],
                )
            return result
        except ImageGenerationError as exc:
            if job_service is not None and tracked_job is not None:
                job_service.fail_inline_job(str(tracked_job.get("id") or ""), exc)
            raise_image_quota_error(exc)
        except Exception as exc:
            if job_service is not None and tracked_job is not None:
                job_service.fail_inline_job(str(tracked_job.get("id") or ""), exc)
            raise

    @router.post("/v1/images/edits")
    async def edit_images(
            request: Request,
            authorization: str | None = Header(default=None),
            image: list[UploadFile] | None = File(default=None),
            image_list: list[UploadFile] | None = File(default=None, alias="image[]"),
            prompt: str = Form(...),
            model: str = Form(default="gpt-image-2"),
            n: int = Form(default=1),
            size: str | None = Form(default=None),
            response_format: str | None = Form(default=None),
            stream: bool | None = Form(default=None),
    ):
        principal = require_client_principal(authorization)
        ensure_model_access(principal, model)
        if n < 1 or n > 4:
            raise HTTPException(status_code=400, detail={"error": "n must be between 1 and 4"})
        reserve_image_quota(principal, n)
        uploads = [*(image or []), *(image_list or [])]
        if not uploads:
            raise HTTPException(status_code=400, detail={"error": "image file is required"})
        base_url = resolve_image_base_url(request)
        request_id = uuid4().hex
        tracking_options = _openai_compat_image_tracking_options()
        images: list[tuple[bytes, str, str]] = []
        for upload in uploads:
            image_data = await upload.read()
            if not image_data:
                raise HTTPException(status_code=400, detail={"error": "image file is empty"})
            images.append((image_data, upload.filename or "image.png", upload.content_type or "image/png"))
        if stream:
            if not account_service.has_available_account():
                raise_image_quota_error(RuntimeError("no available image quota"))
            chunks = chatgpt_service.stream_image_edit(prompt, images, model, n, size, response_format, base_url)
            if job_service is not None and tracking_options["enabled"]:
                tracked_job = job_service.start_inline_job(
                    "images.edits",
                    {
                        "model": model,
                        "prompt": prompt,
                        "n": n,
                        "size": size,
                        "response_format": response_format,
                        "stream": True,
                        "images": ["uploaded"] * len(images),
                    },
                    principal,
                    include_task_tracking=tracking_options["include_task_tracking"],
                )
                chunks = _tracked_image_stream(
                    chunks=chunks,
                    job_service=job_service,
                    job_id=str(tracked_job.get("id") or ""),
                    include_gallery=tracking_options["include_gallery"],
                    include_waterfall=tracking_options["include_waterfall"],
                )
            return StreamingResponse(
                sse_json_stream(chunks),
                media_type="text/event-stream",
            )
        tracked_job: dict[str, object] | None = None
        if job_service is not None and tracking_options["enabled"]:
            tracked_job = job_service.start_inline_job(
                "images.edits",
                {
                    "model": model,
                    "prompt": prompt,
                    "n": n,
                    "size": size,
                    "response_format": response_format,
                    "stream": False,
                    "images": ["uploaded"] * len(images),
                },
                principal,
                include_task_tracking=tracking_options["include_task_tracking"],
            )
            request_id = str(tracked_job.get("id") or "") or request_id
        try:
            result = await run_in_threadpool(
                chatgpt_service.edit_with_pool,
                prompt,
                images,
                model,
                n,
                size,
                response_format,
                base_url,
                request_id,
            )
            if job_service is not None and tracked_job is not None:
                job_service.finish_inline_job(
                    str(tracked_job.get("id") or ""),
                    result,
                    include_gallery=tracking_options["include_gallery"],
                    include_waterfall=tracking_options["include_waterfall"],
                )
            return result
        except ImageGenerationError as exc:
            if job_service is not None and tracked_job is not None:
                job_service.fail_inline_job(str(tracked_job.get("id") or ""), exc)
            raise_image_quota_error(exc)
        except Exception as exc:
            if job_service is not None and tracked_job is not None:
                job_service.fail_inline_job(str(tracked_job.get("id") or ""), exc)
            raise

    @router.post("/v1/chat/completions")
    async def create_chat_completion(body: ChatCompletionRequest, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        payload = body.model_dump(mode="python")
        is_image_request = is_image_chat_request(payload)
        ensure_model_access(principal, payload.get("model") or ("gpt-image-2" if is_image_request else "auto"))
        if bool(payload.get("stream")):
            if is_image_request:
                try:
                    await run_in_threadpool(account_service.get_available_access_token)
                except RuntimeError as exc:
                    raise_image_quota_error(exc)
            return StreamingResponse(
                sse_json_stream(chatgpt_service.stream_chat_completion(payload)),
                media_type="text/event-stream",
            )
        if is_image_request:
            return await _run_tracked_compatible_job(
                job_type="chat.completions",
                payload=payload,
                principal=principal,
                job_service=job_service,
                operation=lambda: chatgpt_service.create_chat_completion(payload),
            )
        return await run_in_threadpool(chatgpt_service.create_chat_completion, payload)

    @router.post("/v1/responses")
    async def create_response(body: ResponseCreateRequest, authorization: str | None = Header(default=None)):
        principal = require_client_principal(authorization)
        payload = body.model_dump(mode="python")
        is_image_request = has_response_image_generation_tool(payload)
        default_model = "gpt-image-2" if is_image_request else "auto"
        ensure_model_access(principal, payload.get("model") or default_model)
        if bool(payload.get("stream")):
            return StreamingResponse(
                responses_sse_stream(chatgpt_service.stream_response(payload)),
                media_type="text/event-stream",
            )
        if is_image_request:
            return await _run_tracked_compatible_job(
                job_type="responses",
                payload=payload,
                principal=principal,
                job_service=job_service,
                operation=lambda: chatgpt_service.create_response(payload),
            )
        return await run_in_threadpool(chatgpt_service.create_response, payload)

    return router
