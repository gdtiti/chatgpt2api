from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import base64
import re
import time
import uuid
from typing import Any, Callable, Iterable, Iterator

from fastapi import HTTPException

from services.account_service import AccountService
from services.config import config
from services.data_service import save_image_bytes
from services.openai_backend_api import CODEX_IMAGE_MODEL, OpenAIBackendAPI
from utils.helper import (
    IMAGE_MODELS,
    extract_chat_image,
    extract_chat_prompt,
    extract_image_from_message_content,
    extract_response_prompt,
    has_response_image_generation_tool,
    parse_image_count,
    build_chat_image_completion,
)
from utils.helper import is_image_chat_request
from utils.log import logger


class ImageGenerationError(Exception):
    pass


def is_token_invalid_error(message: str) -> bool:
    text = str(message or "").lower()
    return (
            "token_invalidated" in text
            or "token_revoked" in text
            or "authentication token has been invalidated" in text
            or "invalidated oauth token" in text
    )


def is_retryable_image_error(message: str) -> bool:
    return "no downloadable image result found" in str(message or "").lower()


def _resolve_image_response_format(response_format: str | None) -> str:
    if config.image_response_format == "url":
        return "url"
    value = str(response_format or "").strip()
    if value in {"b64_json", "url"}:
        return value
    return config.image_response_format


def _should_include_b64_in_url_response(response_format: str | None) -> bool:
    return (
        config.image_response_format == "url"
        and config.image_url_include_b64_when_requested
        and str(response_format or "").strip() == "b64_json"
    )


def _extract_response_images(input_value: object) -> list[tuple[bytes, str]]:
    if isinstance(input_value, dict):
        return extract_image_from_message_content(input_value.get("content"))
    if not isinstance(input_value, list):
        return []
    images: list[tuple[bytes, str]] = []
    for item in reversed(input_value):
        if isinstance(item, dict):
            if str(item.get("type") or "").strip() == "input_image":
                import base64 as b64
                image_url = str(item.get("image_url") or "")
                if image_url.startswith("data:"):
                    header, _, data = image_url.partition(",")
                    mime = header.split(";")[0].removeprefix("data:")
                    images.append((b64.b64decode(data), mime or "image/png"))
            content = item.get("content")
            if content:
                images.extend(extract_image_from_message_content(content))
    return images


class ChatGPTService:
    def __init__(self, account_service: AccountService):
        self.account_service = account_service

    @staticmethod
    def _new_backend(access_token: str = "") -> OpenAIBackendAPI:
        return OpenAIBackendAPI(access_token=access_token)

    def _get_text_access_token(self) -> str:
        tokens = self.account_service.list_tokens()
        return tokens[0] if tokens else ""

    @staticmethod
    def _load_placeholder_result(
            prompt: str,
            response_format: str | None,
            base_url: str | None = None,
            request_id: str | None = None,
            image_index: int = 1,
    ) -> dict[str, object]:
        placeholder_path = config.image_placeholder_path
        if placeholder_path is None:
            raise ImageGenerationError("image placeholder path is not configured")
        if not placeholder_path.is_file():
            raise ImageGenerationError(f"image placeholder file is not found: {placeholder_path}")
        image_bytes = placeholder_path.read_bytes()
        return ChatGPTService._format_image_result(
            {
                "created": int(time.time()),
                "data": [{
                    "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                    "revised_prompt": prompt,
                }],
            },
            prompt,
            response_format,
            base_url,
            request_id=request_id,
            image_index=image_index,
        )

    def _call_image_generation_once(
            self,
            prompt: str,
            model: str,
            size: str | None,
            response_format: str | None,
            base_url: str | None,
            request_id: str | None,
            image_index: int,
    ) -> dict[str, object]:
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                raise ImageGenerationError(str(exc) or "image generation failed") from exc

            logger.info({
                "event": "image_generate_start",
                "request_token": request_token,
                "model": model,
            })
            try:
                result = self._format_image_result(
                    self._new_backend(request_token).images_generations(
                        prompt=prompt,
                        model=model,
                        size=size,
                        response_format="b64_json",
                    ),
                    prompt,
                    response_format,
                    base_url,
                    request_id=request_id,
                    image_index=image_index,
                )
                account = self.account_service.mark_image_result(request_token, success=True)
                image_items = [item for item in result.get("data") or [] if isinstance(item, dict)]
                logger.info({
                    "event": "image_generate_success",
                    "request_token": request_token,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if not image_items:
                    raise ImageGenerationError("image generation failed")
                return {
                    "created": result.get("created"),
                    "data": image_items,
                }
            except Exception as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                logger.warning({
                    "event": "image_generate_fail",
                    "request_token": request_token,
                    "error": message,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if is_token_invalid_error(message):
                    self.account_service.remove_token(request_token)
                    logger.warning({
                        "event": "image_generate_remove_invalid_token",
                        "request_token": request_token,
                    })
                    continue
                raise ImageGenerationError(message or "image generation failed") from exc

    def _call_image_edit_once(
            self,
            prompt: str,
            images: list[tuple[bytes, str, str]],
            model: str,
            size: str | None,
            response_format: str | None,
            base_url: str | None,
            request_id: str | None,
            image_index: int,
    ) -> dict[str, object]:
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                raise ImageGenerationError(str(exc) or "image edit failed") from exc

            logger.info({
                "event": "image_edit_start",
                "request_token": request_token,
                "model": model,
                "image_count": len(images),
            })
            try:
                result = self._format_image_result(
                    self._new_backend(request_token).images_edits(
                        image=self._encode_images(images),
                        prompt=prompt,
                        model=model,
                        size=size,
                        response_format="b64_json",
                    ),
                    prompt,
                    response_format,
                    base_url,
                    request_id=request_id,
                    image_index=image_index,
                )
                account = self.account_service.mark_image_result(request_token, success=True)
                image_items = [item for item in result.get("data") or [] if isinstance(item, dict)]
                logger.info({
                    "event": "image_edit_success",
                    "request_token": request_token,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if not image_items:
                    raise ImageGenerationError("image edit failed")
                return {
                    "created": result.get("created"),
                    "data": image_items,
                }
            except Exception as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                logger.warning({
                    "event": "image_edit_fail",
                    "request_token": request_token,
                    "error": message,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if is_token_invalid_error(message):
                    self.account_service.remove_token(request_token)
                    logger.warning({
                        "event": "image_edit_remove_invalid_token",
                        "request_token": request_token,
                    })
                    continue
                raise ImageGenerationError(message or "image edit failed") from exc

    @staticmethod
    def _first_result_or_raise(
            operation_factory: Callable[[], dict[str, object]],
            parallel_attempts: int,
    ) -> dict[str, object]:
        if parallel_attempts <= 1:
            return operation_factory()
        errors: list[str] = []
        executor = ThreadPoolExecutor(max_workers=parallel_attempts, thread_name_prefix="image-parallel")
        futures: set[Any] = set()
        try:
            futures = {executor.submit(operation_factory) for _ in range(parallel_attempts)}
            pending = set(futures)
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        result = future.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    for pending_future in pending:
                        pending_future.cancel()
                    return result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        raise ImageGenerationError(errors[-1] if errors else "image generation failed")

    def _run_image_operation_with_strategy(
            self,
            *,
            prompt: str,
            response_format: str | None,
            base_url: str | None,
            operation_factory: Callable[[], dict[str, object]],
            request_id: str | None = None,
            image_index: int = 1,
    ) -> dict[str, object]:
        strategy = config.image_failure_strategy
        retry_count = config.image_retry_count if strategy == "retry" else 0
        last_error = ""
        for attempt_index in range(retry_count + 1):
            try:
                return operation_factory()
            except ImageGenerationError as exc:
                last_error = str(exc)
                logger.warning({
                    "event": "image_strategy_fail",
                    "strategy": strategy,
                    "retry_index": attempt_index,
                    "retry_count": retry_count,
                    "parallel_attempts": config.image_parallel_attempts,
                    "error": last_error,
                })
                if not is_retryable_image_error(last_error):
                    raise
                if strategy == "retry" and attempt_index < retry_count:
                    continue
                if strategy == "placeholder":
                    return self._load_placeholder_result(
                        prompt,
                        response_format,
                        base_url,
                        request_id=request_id,
                        image_index=image_index,
                    )
                raise
        raise ImageGenerationError(last_error or "image generation failed")

    @staticmethod
    def _encode_images(images: Iterable[tuple[bytes, str, str]]) -> list[str]:
        encoded_images: list[str] = []
        for image_data, _, _ in images:
            if image_data:
                encoded_images.append(base64.b64encode(image_data).decode("ascii"))
        return encoded_images

    def list_models(self) -> dict[str, object]:
        result = self._new_backend().list_models()
        data = result.get("data")
        if not isinstance(data, list):
            return result
        seen = {str(item.get("id") or "").strip() for item in data if isinstance(item, dict)}
        for model in sorted(IMAGE_MODELS):
            if model in seen:
                continue
            data.append({
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "chatgpt2api",
                "permission": [],
                "root": model,
                "parent": None,
            })
        return result

    @staticmethod
    def _chat_messages_from_body(body: dict[str, object]) -> list[dict[str, object]]:
        messages = body.get("messages")
        if isinstance(messages, list) and messages:
            return [message for message in messages if isinstance(message, dict)]
        prompt = str(body.get("prompt") or "").strip()
        if prompt:
            return [{"role": "user", "content": prompt}]
        raise HTTPException(status_code=400, detail={"error": "messages or prompt is required"})

    @staticmethod
    def _response_messages_from_input(input_value: object, instructions: object = None) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        system_text = str(instructions or "").strip()
        if system_text:
            messages.append({"role": "system", "content": system_text})

        if isinstance(input_value, str):
            user_text = input_value.strip()
            if user_text:
                messages.append({"role": "user", "content": user_text})
            return messages

        if isinstance(input_value, dict):
            messages.append({
                "role": str(input_value.get("role") or "user"),
                "content": extract_response_prompt([input_value]) or input_value.get("content") or "",
            })
            return messages

        if isinstance(input_value, list):
            if all(isinstance(item, dict) and item.get("type") for item in input_value):
                text = extract_response_prompt(input_value)
                if text:
                    messages.append({"role": "user", "content": text})
                return messages
            for item in input_value:
                if not isinstance(item, dict):
                    continue
                messages.append({
                    "role": str(item.get("role") or "user"),
                    "content": extract_response_prompt([item]) or item.get("content") or "",
                })
            return messages

        return messages

    @staticmethod
    def _response_text_output_item(text: str, item_id: str | None = None, status: str = "completed") -> dict[str, object]:
        return {
            "id": item_id or f"msg_{uuid.uuid4().hex}",
            "type": "message",
            "status": status,
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        }

    def _create_text_response(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._response_messages_from_input(body.get("input"), body.get("instructions"))
        if len(messages) == 1 and messages[0].get("role") == "system":
            raise HTTPException(status_code=400, detail={"error": "input text is required"})
        try:
            result = self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        created = int(result.get("created") or time.time())
        output_text = str((((result.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")
        response_id = f"resp_{uuid.uuid4().hex}"
        output_item = self._response_text_output_item(output_text)
        return {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": [output_item],
            "parallel_tool_calls": False,
            "usage": result.get("usage"),
        }

    def _stream_text_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._response_messages_from_input(body.get("input"), body.get("instructions"))
        if len(messages) == 1 and messages[0].get("role") == "system":
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        response_id = f"resp_{uuid.uuid4().hex}"
        item_id = f"msg_{uuid.uuid4().hex}"
        created = int(time.time())
        full_text = ""

        yield {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "in_progress",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [],
                "parallel_tool_calls": False,
            },
        }
        yield {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": self._response_text_output_item("", item_id=item_id, status="in_progress"),
        }

        try:
            stream = self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=True)
            for chunk in stream:
                choices = chunk.get("choices")
                first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                delta = first_choice.get("delta") if isinstance(first_choice.get("delta"), dict) else {}
                delta_text = str(delta.get("content") or "")
                if delta_text:
                    full_text += delta_text
                    yield {
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta_text,
                    }
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        yield {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "text": full_text,
        }
        output_item = self._response_text_output_item(full_text, item_id=item_id, status="completed")
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": output_item,
        }
        yield {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [output_item],
                "parallel_tool_calls": False,
            },
        }

    @staticmethod
    def _is_text_response_request(body: dict[str, object]) -> bool:
        tools = body.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation":
                    return False
        tool_choice = body.get("tool_choice")
        if isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip() == "image_generation":
            return False
        return True

    @staticmethod
    def _is_codex_image_response_request(body: dict[str, object]) -> bool:
        return has_response_image_generation_tool(body) and str(body.get("model") or "").strip() == CODEX_IMAGE_MODEL

    @staticmethod
    def _build_image_response_output(
            prompt: str,
            image_result: dict[str, object],
    ) -> list[dict[str, object]]:
        image_items = image_result.get("data") if isinstance(image_result.get("data"), list) else []
        output: list[dict[str, object]] = []
        for item in image_items:
            if not isinstance(item, dict):
                continue
            b64_json = str(item.get("b64_json") or "").strip()
            image_url = str(item.get("url") or "").strip()
            thumbnail_url = str(item.get("thumbnail_url") or "").strip()
            markdown = str(item.get("markdown") or "").strip()
            result_value = b64_json or image_url
            if not result_value:
                continue
            output_item = {
                "id": f"ig_{len(output) + 1}",
                "type": "image_generation_call",
                "status": "completed",
                "result": result_value,
                "revised_prompt": str(item.get("revised_prompt") or prompt).strip(),
            }
            if image_url:
                output_item["url"] = image_url
            if thumbnail_url:
                output_item["thumbnail_url"] = thumbnail_url
            if markdown:
                output_item["markdown"] = markdown
            output.append(output_item)
        return output

    def _create_token_image_response(self, body: dict[str, object]) -> dict[str, object]:
        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        image_infos = _extract_response_images(body.get("input"))
        try:
            if image_infos:
                images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
                image_result = self.edit_with_pool(prompt, images, model, 1)
            else:
                image_result = self.generate_with_pool(prompt, model, 1, size="1:1")
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        output = self._build_image_response_output(prompt, image_result)
        if not output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        created = int(image_result.get("created") or time.time())
        return {
            "id": f"resp_{created}",
            "object": "response",
            "created_at": created,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": model,
            "output": output,
            "parallel_tool_calls": False,
        }

    def _stream_token_image_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        prompt = extract_response_prompt(body.get("input"))
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "input text is required"})

        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        image_infos = _extract_response_images(body.get("input"))
        response_id = f"resp_{uuid.uuid4().hex}"
        item_id = f"ig_{uuid.uuid4().hex}"
        created = int(time.time())
        final_output: list[dict[str, object]] = []

        yield {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "in_progress",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [],
                "parallel_tool_calls": False,
            },
        }
        yield {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "image_generation_call",
                "status": "in_progress",
                "result": "",
            },
        }

        try:
            if image_infos:
                images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
                stream = self.stream_image_edit(prompt, images, model, 1)
            else:
                stream = self.stream_image_generation(prompt, model, 1, size="1:1")

            for chunk in stream:
                data = chunk.get("data")
                if not isinstance(data, list) or not data:
                    continue
                output = self._build_image_response_output(
                    prompt,
                    {
                        "created": chunk.get("created"),
                        "data": data,
                    },
                )
                if output:
                    final_output = output
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        if not final_output:
            raise HTTPException(status_code=502, detail={"error": "image generation failed"})

        final_item = dict(final_output[0])
        final_item["id"] = item_id
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": final_item,
        }
        yield {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "model": model,
                "output": [final_item],
                "parallel_tool_calls": False,
            },
        }

    @staticmethod
    def _format_image_result(
            result: dict[str, object],
            prompt: str,
            response_format: str | None,
            base_url: str | None = None,
            *,
            request_id: str | None = None,
            image_index: int = 1,
    ) -> dict[str, object]:
        created = result.get("created")
        data = result.get("data")
        normalized_response_format = _resolve_image_response_format(response_format)
        normalized_request_id = str(request_id or uuid.uuid4().hex).strip() or uuid.uuid4().hex
        formatted_items: list[dict[str, object]] = []
        if isinstance(data, list):
            for item_offset, item in enumerate(data, start=0):
                if not isinstance(item, dict):
                    continue
                revised_prompt = str(item.get("revised_prompt") or prompt).strip() or prompt
                b64_json = str(item.get("b64_json") or "").strip()
                if normalized_response_format == "b64_json":
                    if b64_json:
                        formatted_items.append({"b64_json": b64_json, "revised_prompt": revised_prompt})
                    continue
                if not b64_json:
                    continue
                image_data = base64.b64decode(b64_json)
                saved = save_image_bytes(
                    image_data,
                    request_id=normalized_request_id,
                    image_index=image_index + item_offset,
                    base_url=base_url,
                    mime_type=str(item.get("mime_type") or "").strip() or None,
                )
                formatted_item = {
                    "url": saved["url"],
                    "thumbnail_url": saved["thumbnail_url"],
                    "markdown": saved["markdown"],
                    "revised_prompt": revised_prompt,
                }
                if _should_include_b64_in_url_response(response_format):
                    formatted_item["b64_json"] = b64_json
                formatted_items.append(formatted_item)
        return {"created": created, "data": formatted_items}

    @staticmethod
    def _extract_image_data_urls(markdown_content: str) -> list[str]:
        return re.findall(r"!\[[^\]]*\]\((data:image/[^;]+;base64,[^)]+)\)", markdown_content or "")

    def _stream_result_from_markdown(
            self,
            markdown_content: str,
            prompt: str,
            response_format: str,
            base_url: str | None = None,
            created: int | None = None,
            request_id: str | None = None,
            image_index: int = 1,
    ) -> dict[str, object] | None:
        data_urls = self._extract_image_data_urls(markdown_content)
        if not data_urls:
            return None
        raw_items: list[dict[str, object]] = []
        for data_url in data_urls:
            header, _, data = data_url.partition(",")
            mime_type = header.split(";")[0].removeprefix("data:") or "image/png"
            raw_items.append({
                "b64_json": data,
                "revised_prompt": prompt,
                "mime_type": mime_type,
            })
        return self._format_image_result(
            {"created": created or int(time.time()), "data": raw_items},
            prompt,
            response_format,
            base_url,
            request_id=request_id,
            image_index=image_index,
        )

    @staticmethod
    def _progress_chunk(
            model: str,
            index: int,
            total: int,
            created: int | None = None,
            progress_text: str = "",
            upstream_event_type: str = "",
    ) -> dict[str, object]:
        return {
            "object": "image.generation.chunk",
            "created": created or int(time.time()),
            "model": model,
            "index": index,
            "total": total,
            "progress_text": progress_text,
            "upstream_event_type": upstream_event_type,
            "data": [],
        }

    def _stream_single_image_result(
            self,
            prompt: str,
            model: str,
            index: int,
            total: int,
            request_token: str,
            size: str | None = None,
            response_format: str = "b64_json",
            base_url: str | None = None,
            images: list[str] | None = None,
    ) -> Iterator[dict[str, object]]:
        stream = self._new_backend(request_token).stream_image_chat_completions(
            prompt=prompt,
            model=model,
            size=size,
            images=images or None,
        )
        for chunk in stream:
            created = int(chunk.get("created") or time.time()) if isinstance(chunk, dict) else int(time.time())
            choices = chunk.get("choices") if isinstance(chunk, dict) else None
            first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            delta = first_choice.get("delta") if isinstance(first_choice.get("delta"), dict) else {}
            content = str(delta.get("content") or "")
            finish_reason = str(first_choice.get("finish_reason") or "")

            if "upstream_event" in chunk:
                upstream_event = chunk.get("upstream_event")
                upstream_event_type = ""
                if isinstance(upstream_event, dict):
                    upstream_event_type = str(upstream_event.get("type") or "")
                yield self._progress_chunk(model, index, total, created, content, upstream_event_type)
                continue

            formatted_result = self._stream_result_from_markdown(
                content,
                prompt,
                response_format,
                base_url,
                created,
                request_token,
                index,
            )
            if formatted_result:
                yield {
                    "object": "image.generation.result",
                    "created": formatted_result.get("created"),
                    "model": model,
                    "index": index,
                    "total": total,
                    "data": formatted_result.get("data") if isinstance(formatted_result.get("data"), list) else [],
                }
                return

            if finish_reason:
                yield {
                    "object": "image.generation.done",
                    "created": created,
                    "model": model,
                    "index": index,
                    "total": total,
                    "data": [],
                    "finish_reason": finish_reason,
                }

    def _run_generate_slot(
            self,
            prompt: str,
            model: str,
            size: str | None,
            response_format: str | None,
            base_url: str | None,
            request_id: str | None,
            slot_index: int,
            total_slots: int,
    ) -> dict[str, object]:
        logger.info({
            "event": "image_generate_slot_start",
            "model": model,
            "index": slot_index,
            "total": total_slots,
            "parallel_attempts": config.image_parallel_attempts,
        })
        return self._run_image_operation_with_strategy(
            prompt=prompt,
            response_format=response_format,
            base_url=base_url,
            request_id=request_id,
            image_index=slot_index,
            operation_factory=lambda: self._call_image_generation_once(
                prompt,
                model,
                size,
                response_format,
                base_url,
                request_id,
                slot_index,
            ),
        )

    def _run_edit_slot(
            self,
            prompt: str,
            images: list[tuple[bytes, str, str]],
            model: str,
            size: str | None,
            response_format: str | None,
            base_url: str | None,
            request_id: str | None,
            slot_index: int,
            total_slots: int,
    ) -> dict[str, object]:
        logger.info({
            "event": "image_edit_slot_start",
            "model": model,
            "index": slot_index,
            "total": total_slots,
            "image_count": len(images),
            "parallel_attempts": config.image_parallel_attempts,
        })
        return self._run_image_operation_with_strategy(
            prompt=prompt,
            response_format=response_format,
            base_url=base_url,
            request_id=request_id,
            image_index=slot_index,
            operation_factory=lambda: self._call_image_edit_once(
                prompt,
                images,
                model,
                size,
                response_format,
                base_url,
                request_id,
                slot_index,
            ),
        )

    @staticmethod
    def _collect_successful_slots_or_raise(
            total_slots: int,
            requested_count: int,
            operation_factory: Callable[[int], dict[str, object]],
    ) -> list[dict[str, object]]:
        if total_slots <= 1:
            return [operation_factory(1)]
        errors: list[str] = []
        successful_results: list[dict[str, object]] = []
        executor = ThreadPoolExecutor(max_workers=total_slots, thread_name_prefix="image-fastest")
        futures: dict[Any, int] = {}
        try:
            for slot_index in range(1, total_slots + 1):
                futures[executor.submit(operation_factory, slot_index)] = slot_index
            pending = set(futures)
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    slot_index = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    logger.info({
                        "event": "image_slot_return_success",
                        "slot_index": slot_index,
                        "total_slots": total_slots,
                        "requested_count": requested_count,
                        "successful_count": len(successful_results) + 1,
                    })
                    successful_results.append(result)
                    if len(successful_results) >= requested_count:
                        for pending_future in pending:
                            pending_future.cancel()
                        return successful_results
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if successful_results:
            logger.warning({
                "event": "image_slot_partial_success",
                "requested_count": requested_count,
                "successful_count": len(successful_results),
                "total_slots": total_slots,
                "error_count": len(errors),
            })
            return successful_results
        raise ImageGenerationError(errors[-1] if errors else "image generation failed")

    @staticmethod
    def _image_total_slots(requested_count: int) -> int:
        extra_slots = max(0, int(config.image_parallel_attempts) - 1)
        return max(1, int(requested_count or 1)) + extra_slots

    def generate_with_pool(
            self,
            prompt: str,
            model: str,
            n: int,
            size: str | None = None,
            response_format: str | None = None,
            base_url: str = None,
            request_id: str | None = None,
    ):
        requested_count = max(1, int(n or 1))
        total_slots = self._image_total_slots(requested_count)
        results = self._collect_successful_slots_or_raise(
            total_slots,
            requested_count,
            lambda slot_index: self._run_generate_slot(
                prompt,
                model,
                size,
                response_format,
                base_url,
                request_id,
                slot_index,
                total_slots,
            ),
        )
        created = None
        image_items: list[dict[str, object]] = []
        for result in results[:requested_count]:
            if created is None:
                created = result.get("created")
            image_items.extend(item for item in result.get("data") or [] if isinstance(item, dict))
        return {
            "created": created,
            "data": image_items,
        }

    def stream_image_generation(
            self,
            prompt: str,
            model: str,
            n: int,
            size: str | None = None,
            response_format: str | None = None,
            base_url: str | None = None,
    ) -> Iterator[dict[str, object]]:
        last_error = ""
        emitted = False
        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_generate_stream_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    if emitted:
                        return
                    raise ImageGenerationError(last_error or "image generation failed") from exc

                logger.info({
                    "event": "image_generate_stream_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                })
                emitted_for_request = False
                has_result = False
                try:
                    for chunk in self._stream_single_image_result(
                            prompt,
                            model,
                            index,
                            n,
                            request_token,
                            size,
                            response_format,
                            base_url,
                    ):
                        emitted = True
                        emitted_for_request = True
                        data = chunk.get("data")
                        if isinstance(data, list) and data:
                            has_result = True
                        yield chunk
                    if not has_result:
                        last_error = "image generation failed"
                        raise ImageGenerationError(last_error)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    logger.info({
                        "event": "image_generate_stream_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                        "has_result": has_result,
                    })
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_generate_stream_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if not emitted_for_request and is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_generate_stream_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    raise ImageGenerationError(last_error or "image generation failed") from exc

    def edit_with_pool(
            self,
            prompt: str,
            images: Iterable[tuple[bytes, str, str]],
            model: str,
            n: int,
            size: str | None = None,
            response_format: str | None = None,
            base_url: str = None,
            request_id: str | None = None,
    ):
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")
        requested_count = max(1, int(n or 1))
        total_slots = self._image_total_slots(requested_count)
        results = self._collect_successful_slots_or_raise(
            total_slots,
            requested_count,
            lambda slot_index: self._run_edit_slot(
                prompt,
                normalized_images,
                model,
                size,
                response_format,
                base_url,
                request_id,
                slot_index,
                total_slots,
            ),
        )
        created = None
        image_items: list[dict[str, object]] = []
        for result in results[:requested_count]:
            if created is None:
                created = result.get("created")
            image_items.extend(item for item in result.get("data") or [] if isinstance(item, dict))
        return {
            "created": created,
            "data": image_items,
        }

    def stream_image_edit(
            self,
            prompt: str,
            images: Iterable[tuple[bytes, str, str]],
            model: str,
            n: int,
            size: str | None = None,
            response_format: str | None = None,
            base_url: str | None = None,
    ) -> Iterator[dict[str, object]]:
        last_error = ""
        emitted = False
        normalized_images = list(images)
        if not normalized_images:
            raise ImageGenerationError("image is required")
        encoded_images = self._encode_images(normalized_images)

        for index in range(1, n + 1):
            while True:
                try:
                    request_token = self.account_service.get_available_access_token()
                except RuntimeError as exc:
                    last_error = str(exc)
                    logger.warning({
                        "event": "image_edit_stream_stop",
                        "index": index,
                        "total": n,
                        "error": last_error,
                    })
                    if emitted:
                        return
                    raise ImageGenerationError(last_error or "image edit failed") from exc

                logger.info({
                    "event": "image_edit_stream_start",
                    "request_token": request_token,
                    "model": model,
                    "index": index,
                    "total": n,
                    "image_count": len(normalized_images),
                })
                emitted_for_request = False
                has_result = False
                try:
                    for chunk in self._stream_single_image_result(
                            prompt=prompt,
                            model=model,
                            index=index,
                            total=n,
                            request_token=request_token,
                            size=size,
                            response_format=response_format,
                            base_url=base_url,
                            images=encoded_images,
                    ):
                        emitted = True
                        emitted_for_request = True
                        data = chunk.get("data")
                        if isinstance(data, list) and data:
                            has_result = True
                        yield chunk
                    if not has_result:
                        last_error = "image edit failed"
                        raise ImageGenerationError(last_error)
                    account = self.account_service.mark_image_result(request_token, success=True)
                    logger.info({
                        "event": "image_edit_stream_success",
                        "request_token": request_token,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                        "has_result": has_result,
                    })
                    break
                except Exception as exc:
                    account = self.account_service.mark_image_result(request_token, success=False)
                    message = str(exc)
                    last_error = message
                    logger.warning({
                        "event": "image_edit_stream_fail",
                        "request_token": request_token,
                        "error": message,
                        "quota": account.get("quota") if account else "unknown",
                        "status": account.get("status") if account else "unknown",
                    })
                    if not emitted_for_request and is_token_invalid_error(message):
                        self.account_service.remove_token(request_token)
                        logger.warning({
                            "event": "image_edit_stream_remove_invalid_token",
                            "request_token": request_token,
                        })
                        continue
                    raise ImageGenerationError(last_error or "image edit failed") from exc

    @staticmethod
    def _stream_completion_response(result: dict[str, object]) -> Iterator[dict[str, object]]:
        completion_id = str(result.get("id") or f"chatcmpl-{uuid.uuid4().hex}")
        created = int(result.get("created") or time.time())
        model = str(result.get("model") or "auto")
        choices = result.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
        content = str(message.get("content") or "")
        finish_reason = str(first_choice.get("finish_reason") or "stop")

        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": content},
                "finish_reason": None,
            }],
        }
        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }],
        }

    def _create_image_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        n = parse_image_count(body.get("n"))
        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        image_infos = extract_chat_image(body)
        try:
            if image_infos:
                images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
                image_result = self.edit_with_pool(prompt, images, model, n)
            else:
                image_result = self.generate_with_pool(prompt, model, n, size="1:1")
        except ImageGenerationError as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

        return build_chat_image_completion(model, image_result)

    def _stream_image_chat_completion(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        model = str(body.get("model") or "gpt-image-2").strip() or "gpt-image-2"
        n = parse_image_count(body.get("n"))
        if n != 1:
            result = self._create_image_chat_completion(body)
            yield from self._stream_completion_response(result)
            return

        prompt = extract_chat_prompt(body)
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        image_infos = extract_chat_image(body)
        encoded_images = []
        if image_infos:
            images = [(data, f"image_{idx}.png", mime) for idx, (data, mime) in enumerate(image_infos, start=1)]
            encoded_images = self._encode_images(images)

        last_error = ""
        while True:
            try:
                request_token = self.account_service.get_available_access_token()
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

            logger.info({
                "event": "image_stream_start",
                "request_token": request_token,
                "model": model,
            })
            emitted = False
            try:
                stream = self._new_backend(request_token).stream_image_chat_completions(
                    prompt=prompt,
                    model=model,
                    size="1:1",
                    images=encoded_images or None,
                )
                for chunk in stream:
                    emitted = True
                    yield chunk
                account = self.account_service.mark_image_result(request_token, success=True)
                logger.info({
                    "event": "image_stream_success",
                    "request_token": request_token,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                return
            except Exception as exc:
                account = self.account_service.mark_image_result(request_token, success=False)
                message = str(exc)
                last_error = message
                logger.warning({
                    "event": "image_stream_fail",
                    "request_token": request_token,
                    "error": message,
                    "quota": account.get("quota") if account else "unknown",
                    "status": account.get("status") if account else "unknown",
                })
                if not emitted and is_token_invalid_error(message):
                    self.account_service.remove_token(request_token)
                    logger.warning({
                        "event": "image_stream_remove_invalid_token",
                        "request_token": request_token,
                    })
                    continue
                raise HTTPException(status_code=502, detail={"error": last_error or "image generation failed"}) from exc

    def _create_text_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._chat_messages_from_body(body)
        try:
            return self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_chat_completion(self, body: dict[str, object]) -> dict[str, object]:
        if is_image_chat_request(body):
            return self._create_image_chat_completion(body)
        return self._create_text_chat_completion(body)

    def stream_chat_completion(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        if is_image_chat_request(body):
            yield from self._stream_image_chat_completion(body)
            return

        model = str(body.get("model") or "auto").strip() or "auto"
        messages = self._chat_messages_from_body(body)
        try:
            yield from self._new_backend(self._get_text_access_token()).chat_completions(messages=messages, model=model, stream=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_image_completion(self, body: dict[str, object]) -> dict[str, object]:
        if not is_image_chat_request(body):
            raise HTTPException(
                status_code=400,
                detail={"error": "only image generation requests are supported on this endpoint"},
            )
        return self._create_image_chat_completion(body)

    def _get_response_access_token(self, body: dict[str, object]) -> str:
        return self.account_service.get_available_access_token()

    def stream_response(self, body: dict[str, object]) -> Iterator[dict[str, object]]:
        if self._is_text_response_request(body):
            yield from self._stream_text_response(body)
            return
        if not self._is_codex_image_response_request(body):
            yield from self._stream_token_image_response(body)
            return
        try:
            access_token = self._get_response_access_token(body)
            yield from self._new_backend(access_token).responses(
                input=body.get("input") or "",
                model=str(body.get("model") or "gpt-5.4").strip() or "gpt-5.4",
                tools=body.get("tools") if isinstance(body.get("tools"), list) else None,
                instructions=str(body.get("instructions") or "you are a helpful assistant"),
                tool_choice=body.get("tool_choice") or "auto",
                stream=True,
                store=bool(body.get("store")),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc

    def create_response(self, body: dict[str, object]) -> dict[str, object]:
        if self._is_text_response_request(body):
            return self._create_text_response(body)
        if not self._is_codex_image_response_request(body):
            return self._create_token_image_response(body)
        try:
            access_token = self._get_response_access_token(body)
            return self._new_backend(access_token).responses(
                input=body.get("input") or "",
                model=str(body.get("model") or "gpt-5.4").strip() or "gpt-5.4",
                tools=body.get("tools") if isinstance(body.get("tools"), list) else None,
                instructions=str(body.get("instructions") or "you are a helpful assistant"),
                tool_choice=body.get("tool_choice") or "auto",
                stream=False,
                store=bool(body.get("store")),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
