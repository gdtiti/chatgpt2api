from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.ai as ai_module
import api.app as app_module
import api.support as support_module
from api import create_app
from services.api_key_service import APIKeyService
from services.chatgpt_service import ImageGenerationError
from services.job_service import JobService
from utils.log import logger


class _DelayedChatGPTService:
    def __init__(self, *, delay: float = 0.0):
        self.delay = delay
        self.last_image_generation: dict[str, object] | None = None
        self.last_image_edit: dict[str, object] | None = None

    def list_models(self) -> dict[str, object]:
        return {"object": "list", "data": [{"id": "auto", "object": "model", "owned_by": "chatgpt2api"}]}

    def create_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        time.sleep(self.delay)
        if str(payload.get("model") or "").strip() == "gpt-image-2":
            content = "![generated](/api/view/data/2026-04-25/chat-image-1.png)"
        else:
            content = "done"
        return {
            "id": "chatcmpl_async",
            "object": "chat.completion",
            "created": 1,
            "model": payload.get("model") or "auto",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        }

    def stream_chat_completion(self, payload: dict[str, object]):
        time.sleep(self.delay)
        model = payload.get("model") or "auto"
        completion_id = "chatcmpl_stream"
        if str(model).strip() == "gpt-image-2":
            content = "![generated](/api/view/data/2026-04-25/chat-stream-1.png)"
        else:
            content = "done"
        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
        }
        yield {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": 1,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        time.sleep(self.delay)
        tools = payload.get("tools")
        if isinstance(tools, list) and any(
                isinstance(tool, dict) and str(tool.get("type") or "").strip() == "image_generation"
                for tool in tools
        ):
            return {
                "id": "resp_async",
                "object": "response",
                "output": [{
                    "id": "ig_1",
                    "type": "image_generation_call",
                    "status": "completed",
                    "result": "/api/view/data/2026-04-25/response-image-1.png",
                    "url": "/api/view/data/2026-04-25/response-image-1.png",
                    "thumbnail_url": "/api/view/data/2026-04-25/response-image-1-thumb.png",
                }],
            }
        return {"id": "resp_async", "object": "response", "output": []}

    def stream_response(self, payload: dict[str, object]):
        time.sleep(self.delay)
        yield {
            "type": "response.created",
            "response": {
                "id": "resp_stream",
                "object": "response",
                "created_at": 1,
                "status": "in_progress",
                "model": payload.get("model") or "auto",
                "output": [],
            },
        }
        yield {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "id": "ig_1",
                "type": "image_generation_call",
                "status": "completed",
                "result": "/api/view/data/2026-04-25/demo-1.png",
                "url": "/api/view/data/2026-04-25/demo-1.png",
                "thumbnail_url": "/api/view/data/2026-04-25/demo-1-thumb.png",
            },
        }
        yield {
            "type": "response.completed",
            "response": {
                "id": "resp_stream",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": payload.get("model") or "auto",
                "output": [],
            },
        }

    def stream_image_generation(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        quality: str | None = None,
        request_id: str | None = None,
    ):
        time.sleep(self.delay)
        self.last_image_generation = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "request_id": request_id,
            "quality": quality,
        }
        yield {
            "object": "image.generation.result",
            "created": 1,
            "model": model,
            "index": 1,
            "total": n,
            "data": [{
                "url": "/api/view/data/2026-04-25/stream-job-1.png",
                "thumbnail_url": "/api/view/data/2026-04-25/stream-job-1-thumb.png",
                "revised_prompt": prompt,
            }],
        }

    def stream_image_edit(
        self,
        prompt: str,
        images,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
    ):
        image_items = list(images)
        time.sleep(self.delay)
        self.last_image_edit = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "request_id": request_id,
            "image_count": len(image_items),
        }
        yield {
            "object": "image.generation.result",
            "created": 1,
            "model": model,
            "index": 1,
            "total": n,
            "data": [{
                "url": "/api/view/data/2026-04-25/edit-stream-job-1.png",
                "thumbnail_url": "/api/view/data/2026-04-25/edit-stream-job-1-thumb.png",
                "revised_prompt": prompt,
            }],
        }

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
        quality: str | None = None,
    ):
        time.sleep(self.delay)
        self.last_image_generation = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "request_id": request_id,
            "quality": quality,
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    def edit_with_pool(
        self,
        prompt: str,
        images,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
    ):
        time.sleep(self.delay)
        self.last_image_edit = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "request_id": request_id,
            "image_count": len(list(images)),
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}


class _AvailableAccountService:
    def get_available_access_token(self) -> str:
        return "fake-access-token"

    def has_available_account(self) -> bool:
        return True


class _PartialImageChatGPTService(_DelayedChatGPTService):
    def __init__(self) -> None:
        super().__init__(delay=0.0)
        self.first_yielded = threading.Event()
        self.release_second = threading.Event()

    def stream_image_generation(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        quality: str | None = None,
        request_id: str | None = None,
    ):
        yield {
            "object": "image.generation.result",
            "created": 1,
            "model": model,
            "index": 1,
            "total": n,
            "data": [{"b64_json": "Zmlyc3Q=", "revised_prompt": prompt}],
        }
        self.first_yielded.set()
        self.release_second.wait(timeout=5.0)
        yield {
            "object": "image.generation.result",
            "created": 1,
            "model": model,
            "index": 2,
            "total": n,
            "data": [{"b64_json": "c2Vjb25k", "revised_prompt": prompt}],
        }


class _FailingImageChatGPTService(_DelayedChatGPTService):
    def stream_image_generation(self, *_args, **_kwargs):
        raise ImageGenerationError("no downloadable image result found; conversation_id=test, file_ids=[], sediment_ids=[]")
        yield

    def generate_with_pool(self, *_args, **_kwargs):
        raise ImageGenerationError("no downloadable image result found; conversation_id=test, file_ids=[], sediment_ids=[]")


class _PartialThenFailingImageChatGPTService(_DelayedChatGPTService):
    def stream_image_generation(self, prompt: str, model: str, n: int, *_args, **_kwargs):
        yield {
            "object": "image.generation.result",
            "created": 1,
            "model": model,
            "index": 1,
            "total": n,
            "data": [{"b64_json": "cGFydGlhbA==", "revised_prompt": prompt}],
        }
        raise ImageGenerationError("no downloadable image result found; conversation_id=test, file_ids=[], sediment_ids=[]")


class AsyncJobRouteTests(unittest.TestCase):
    @staticmethod
    def _iter_sse_events(stream_response):
        event_name = "message"
        for line in stream_response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("event:"):
                event_name = text[6:].strip() or "message"
                continue
            if not text.startswith("data:"):
                continue
            payload = text[5:].strip()
            if payload == "[DONE]":
                yield "done", payload
                return
            yield event_name, json.loads(payload)
            event_name = "message"

    def test_empty_metadata_backfill_is_attempted_once_per_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="empty-client")
            principal = api_key_service.authenticate(created["plain_text"])
            self.assertIsNotNone(principal)
            assert principal is not None

            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                _DelayedChatGPTService(delay=0.0),
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )
            scan_calls: list[str] = []

            def fake_scan(*args, **kwargs):
                scan_calls.append("scan")
                return []

            try:
                job_service._scan_job_files = fake_scan  # type: ignore[method-assign]

                job_service.list_jobs(principal)
                job_service.summarize_jobs(principal)
                job_service.list_gallery_jobs(principal)
                job_service.list_waterfall_images(principal)

                self.assertEqual(len(scan_calls), 1)
            finally:
                job_service.shutdown(wait=False)

    def test_async_job_list_supports_filters_and_tracking_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            principal = api_key_service.authenticate(client_key)
            self.assertIsNotNone(principal)
            assert principal is not None

            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            jobs_dir = Path(tmp_dir) / "jobs"
            results_dir = Path(tmp_dir) / "job_results"
            task_logs_dir = Path(tmp_dir) / "task_logs"
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(jobs_dir, results_dir, fake_chatgpt_service, task_logs_dir=task_logs_dir, max_workers=1)

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                now = "2026-04-25T00:00:00Z"
                job_service._write_json(
                    jobs_dir / "job-chat.json",
                    {
                        "id": "job-chat",
                        "type": "chat.completions",
                        "status": "running",
                        "model": "auto",
                        "created_at": now,
                        "updated_at": now,
                        "api_key_id": principal.key_id,
                        "api_key_name": principal.name,
                        "payload": {
                            "messages": [{"role": "user", "content": "请生成一张封面图"}],
                            "n": 2,
                        },
                        "error": None,
                    },
                )
                job_service._write_json(
                    jobs_dir / "job-image.json",
                    {
                        "id": "job-image",
                        "type": "images.generations",
                        "status": "succeeded",
                        "model": "gpt-image-2",
                        "created_at": now,
                        "updated_at": now,
                        "api_key_id": principal.key_id,
                        "api_key_name": principal.name,
                        "payload": {
                            "prompt": "生成一张海边日落海报",
                            "size": "16:9",
                            "n": 1,
                        },
                        "error": None,
                    },
                )
                job_service._write_json(
                    results_dir / "job-image.json",
                    {"result": {"created": 1, "data": [{"b64_json": "ZmFrZQ=="}]}},
                )

                response = client.get(
                    "/api/async/jobs?type=images.generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["summary"]["total"], 2)
                self.assertEqual(payload["summary"]["running"], 1)
                self.assertEqual(payload["summary"]["succeeded"], 1)
                self.assertEqual(len(payload["items"]), 1)
                item = payload["items"][0]
                self.assertEqual(item["id"], "job-image")
                self.assertEqual(item["api_key_name"], "async-client")
                self.assertEqual(item["prompt_preview"], "生成一张海边日落海报")
                self.assertEqual(item["size"], "16:9")
                self.assertEqual(item["requested_count"], 1)
                self.assertEqual(item["result_ready"], True)
                self.assertEqual(item["result_count"], 1)

                running_response = client.get(
                    "/api/async/jobs?status=running",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(running_response.status_code, 200)
                running_items = running_response.json()["items"]
                self.assertEqual(len(running_items), 1)
                self.assertEqual(running_items[0]["id"], "job-chat")
                self.assertEqual(running_items[0]["prompt_preview"], "请生成一张封面图")
                self.assertEqual(running_items[0]["requested_count"], 2)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_job_records_survive_when_json_files_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="persistent-client")
            principal = api_key_service.authenticate(created["plain_text"])
            self.assertIsNotNone(principal)
            assert principal is not None

            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                _DelayedChatGPTService(delay=0.0),
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )
            try:
                public_job = {
                    "id": "db-only-job",
                    "type": "images.generations",
                    "status": "succeeded",
                    "model": "gpt-image-2",
                    "created_at": "2026-04-25T00:00:00Z",
                    "updated_at": "2026-04-25T00:01:00Z",
                    "log_path": str(Path(tmp_dir) / "task_logs" / "db-only-job.log"),
                    "api_key_id": principal.key_id,
                    "api_key_name": principal.name,
                    "prompt_preview": "数据库持久化图片",
                    "requested_count": 1,
                    "size": "1:1",
                    "input_image_count": 0,
                    "result_ready": True,
                    "result_count": 1,
                    "preview_images": [],
                    "error": None,
                }
                preview_images = [{
                    "id": "image-1",
                    "src": "/api/view/data/2026-04-25/db-only-job-1-thumb.png",
                    "url": "/api/view/data/2026-04-25/db-only-job-1.png",
                    "thumbnail_url": "/api/view/data/2026-04-25/db-only-job-1-thumb.png",
                    "wall_url": "/api/view/data/2026-04-25/db-only-job-1-wall.png",
                    "relative_path": "2026-04-25/db-only-job-1.png",
                    "thumbnail_relative_path": "2026-04-25/db-only-job-1-thumb.png",
                    "wall_relative_path": "2026-04-25/db-only-job-1-wall.png",
                }]
                result_payload = {"result": {"created": 1, "data": [{"url": preview_images[0]["url"]}]}}

                job_service.metadata_db.record_async_job(
                    public_job,
                    payload={"prompt": "数据库持久化图片", "size": "1:1", "n": 1},
                    preview_images=preview_images,
                    result=result_payload,
                )

                listed_jobs, jobs_total = job_service.list_jobs(principal)
                self.assertEqual(jobs_total, 1)
                self.assertEqual(listed_jobs[0]["id"], "db-only-job")

                gallery_jobs, gallery_total = job_service.list_gallery_jobs(principal)
                self.assertEqual(gallery_total, 1)
                self.assertEqual(gallery_jobs[0]["preview_images"][0]["relative_path"], "2026-04-25/db-only-job-1.png")

                wall_items, wall_total = job_service.list_waterfall_images(principal)
                self.assertEqual(wall_total, 1)
                self.assertEqual(wall_items[0]["wall_relative_path"], "2026-04-25/db-only-job-1-wall.png")

                loaded_job = job_service.get_job("db-only-job", principal)
                self.assertIsNotNone(loaded_job)
                assert loaded_job is not None
                self.assertEqual(loaded_job["prompt_preview"], "数据库持久化图片")

                result_job, result = job_service.get_job_result("db-only-job", principal)
                self.assertIsNotNone(result_job)
                self.assertEqual(result, result_payload)
            finally:
                job_service.shutdown(wait=False)

    def test_async_job_result_and_sse_ping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.2)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={"type": "chat.completions", "payload": {"messages": [{"role": "user", "content": "hi"}]}},
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                with client.stream(
                        "GET",
                        f"/api/async/jobs/{job_id}/events?ping_interval=1",
                        headers={"Authorization": f"Bearer {client_key}"},
                ) as stream_response:
                    self.assertEqual(stream_response.status_code, 200)
                    lines = []
                    for line in stream_response.iter_lines():
                        if not line:
                            continue
                        text = line.decode("utf-8") if isinstance(line, bytes) else line
                        lines.append(text)
                        if text == "data: [DONE]":
                            break
                    self.assertTrue(any(line == "event: ping" for line in lines))
                    self.assertTrue(any(line == "event: result" for line in lines))

                deadline = time.time() + 3
                while time.time() < deadline:
                    result_response = client.get(
                        f"/api/async/jobs/{job_id}/result",
                        headers={"Authorization": f"Bearer {client_key}"},
                    )
                    if result_response.status_code == 200:
                        break
                    time.sleep(0.05)
                self.assertEqual(result_response.status_code, 200)
                self.assertEqual(result_response.json()["result"]["id"], "chatcmpl_async")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_job_list_extracts_response_preview_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            principal = api_key_service.authenticate(client_key)
            self.assertIsNotNone(principal)
            assert principal is not None

            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            jobs_dir = Path(tmp_dir) / "jobs"
            results_dir = Path(tmp_dir) / "job_results"
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                jobs_dir,
                results_dir,
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                now = "2026-04-25T00:00:00Z"
                job_service._write_json(
                    jobs_dir / "job-response.json",
                    {
                        "id": "job-response",
                        "type": "responses",
                        "status": "succeeded",
                        "model": "gpt-image-2",
                        "created_at": now,
                        "updated_at": now,
                        "api_key_id": principal.key_id,
                        "api_key_name": principal.name,
                        "payload": {
                            "model": "gpt-image-2",
                            "input": "make image",
                        },
                        "error": None,
                    },
                )
                job_service._write_json(
                    results_dir / "job-response.json",
                    {
                        "result": {
                            "id": "resp_1",
                            "object": "response",
                            "output": [
                                {
                                    "id": "ig_1",
                                    "type": "image_generation_call",
                                    "status": "completed",
                                    "result": "/api/view/data/2026-04-25/demo-1.png",
                                    "url": "/api/view/data/2026-04-25/demo-1.png",
                                    "thumbnail_url": "/api/view/data/2026-04-25/demo-1-thumb.png",
                                }
                            ],
                        }
                    },
                )

                response = client.get("/api/async/jobs?type=responses", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(response.status_code, 200)
                items = response.json()["items"]
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["id"], "job-response")
                self.assertEqual(items[0]["preview_images"][0]["src"], "/api/view/data/2026-04-25/demo-1-thumb.png")
                self.assertEqual(items[0]["preview_images"][0]["url"], "/api/view/data/2026-04-25/demo-1.png")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_responses_stream_uses_typed_sse_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                with client.stream(
                    "POST",
                    "/v1/responses",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={"model": "gpt-image-2", "input": "draw", "tools": [{"type": "image_generation"}], "stream": True},
                ) as response:
                    self.assertEqual(response.status_code, 200)
                    lines = []
                    for line in response.iter_lines():
                        if not line:
                            continue
                        lines.append(line.decode("utf-8") if isinstance(line, bytes) else line)

                self.assertIn("event: response.created", lines)
                self.assertIn("event: response.output_item.done", lines)
                self.assertTrue(any(line.startswith("data: {") and "\"type\": \"response.output_item.done\"" in line for line in lines))
                self.assertEqual(lines[-1], "data: [DONE]")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_image_job_passes_size_and_quality_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "type": "images.generations",
                        "payload": {
                            "model": "gpt-image-2",
                            "prompt": "make image",
                            "n": 1,
                            "size": "1536x1024",
                            "quality": "medium",
                            "response_format": "b64_json",
                        },
                    },
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                deadline = time.time() + 3
                while time.time() < deadline:
                    result_response = client.get(
                        f"/api/async/jobs/{job_id}/result",
                        headers={"Authorization": f"Bearer {client_key}"},
                    )
                    if result_response.status_code == 200:
                        break
                    time.sleep(0.05)

                self.assertEqual(result_response.status_code, 200)
                self.assertIsNotNone(fake_chatgpt_service.last_image_generation)
                self.assertEqual(fake_chatgpt_service.last_image_generation["size"], "1536x1024")
                self.assertEqual(fake_chatgpt_service.last_image_generation["quality"], "medium")
                self.assertEqual(fake_chatgpt_service.last_image_generation["request_id"], job_id)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_image_conversations_are_global_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            first_key = api_key_service.create_key(name="first-client")["plain_text"]
            second_key = api_key_service.create_key(name="second-client")["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))
                conversation = {
                    "id": "conversation-1",
                    "title": "persistent image chat",
                    "createdAt": "2026-04-28T00:00:00Z",
                    "updatedAt": "2026-04-28T00:01:00Z",
                    "turns": [{
                        "id": "turn-1",
                        "prompt": "draw",
                        "model": "gpt-image-2",
                        "mode": "generate",
                        "requestMode": "async_sse",
                        "count": 1,
                        "referenceImages": [],
                        "images": [{"id": "image-1", "status": "success", "url": "/api/view/data/demo.png"}],
                        "createdAt": "2026-04-28T00:01:00Z",
                        "status": "success",
                    }],
                }

                save_response = client.put(
                    "/api/image/conversations/conversation-1",
                    headers={"Authorization": f"Bearer {first_key}"},
                    json={"conversation": conversation},
                )
                self.assertEqual(save_response.status_code, 200)

                first_response = client.get(
                    "/api/image/conversations",
                    headers={"Authorization": f"Bearer {first_key}"},
                )
                self.assertEqual(first_response.status_code, 200)
                self.assertEqual(first_response.json()["items"], [conversation])

                second_response = client.get(
                    "/api/image/conversations",
                    headers={"Authorization": f"Bearer {second_key}"},
                )
                self.assertEqual(second_response.status_code, 200)
                self.assertEqual(second_response.json()["items"], [conversation])

                delete_response = client.delete(
                    "/api/image/conversations/conversation-1",
                    headers={"Authorization": f"Bearer {second_key}"},
                )
                self.assertEqual(delete_response.status_code, 200)
                self.assertTrue(delete_response.json()["deleted"])
                empty_response = client.get(
                    "/api/image/conversations",
                    headers={"Authorization": f"Bearer {first_key}"},
                )
                self.assertEqual(empty_response.json()["items"], [])
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_job_writes_task_log_and_system_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            system_log_path = Path(tmp_dir) / "system.log"
            task_logs_dir = Path(tmp_dir) / "task_logs"
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(system_log_path)
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=task_logs_dir,
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={"type": "chat.completions", "payload": {"messages": [{"role": "user", "content": "hi"}]}},
                )
                self.assertEqual(submit_response.status_code, 200)
                job = submit_response.json()["job"]

                deadline = time.time() + 3
                while time.time() < deadline:
                    result_response = client.get(
                        f"/api/async/jobs/{job['id']}/result",
                        headers={"Authorization": f"Bearer {client_key}"},
                    )
                    if result_response.status_code == 200:
                        break
                    time.sleep(0.05)

                self.assertEqual(result_response.status_code, 200)
                task_log_path = Path(job["log_path"])
                self.assertTrue(task_log_path.exists())
                self.assertTrue(system_log_path.exists())
                task_log_text = task_log_path.read_text(encoding="utf-8")
                system_log_text = system_log_path.read_text(encoding="utf-8")
                self.assertIn("async_job_submitted", task_log_text)
                self.assertIn("async_job_started", task_log_text)
                self.assertIn("async_job_succeeded", task_log_text)
                self.assertIn(job["id"], task_log_text)
                self.assertIn(job["id"], system_log_text)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_job_log_endpoint_returns_log_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={"type": "chat.completions", "payload": {"messages": [{"role": "user", "content": "hi"}]}},
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                deadline = time.time() + 3
                while time.time() < deadline:
                    response = client.get(
                        f"/api/async/jobs/{job_id}/log",
                        headers={"Authorization": f"Bearer {client_key}"},
                    )
                    if response.status_code == 200 and "async_job_succeeded" in response.json()["log_text"]:
                        break
                    time.sleep(0.05)

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["job"]["id"], job_id)
                self.assertIn("async_job_started", payload["log_text"])
                self.assertIn("async_job_succeeded", payload["log_text"])
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_image_job_respects_image_quota(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(
                name="quota-client",
                allowed_models=["gpt-image-2"],
                max_image_count=1,
            )
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "type": "images.generations",
                        "payload": {
                            "model": "gpt-image-2",
                            "prompt": "quota test",
                            "n": 2,
                        },
                    },
                )
                self.assertEqual(response.status_code, 429)
                detail = response.json()["detail"]
                error_message = detail["error"] if isinstance(detail, dict) else json.dumps(detail, ensure_ascii=False)
                self.assertIn("image quota exceeded", error_message)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_stream_image_generation_creates_trackable_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="stream-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            old_ai_account_service = ai_module.account_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                ai_module.account_service = _AvailableAccountService()
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "model": "gpt-image-2",
                        "prompt": "tracked stream image",
                        "n": 1,
                        "size": "1:1",
                        "response_format": "url",
                        "stream": True,
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("data: [DONE]", response.text)
                self.assertIn("job_id", response.text)

                jobs_response = client.get(
                    "/api/async/jobs?type=images.generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                payload = jobs_response.json()
                self.assertEqual(payload["total"], 1)
                job = payload["items"][0]
                self.assertEqual(job["status"], "succeeded")
                self.assertEqual(job["prompt_preview"], "tracked stream image")
                self.assertEqual(job["result_count"], 1)
                self.assertEqual(len(job["preview_images"]), 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                ai_module.account_service = old_ai_account_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_openai_image_api_failure_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="sync-failure-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _FailingImageChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={"model": "gpt-image-2", "prompt": "sync fail", "n": 1},
                )

                self.assertEqual(response.status_code, 502)
                detail = response.json()["detail"]
                self.assertEqual(detail["code"], "image_result_not_found")
                self.assertEqual(detail["status_code"], 502)
                self.assertIn("no downloadable image result found", detail["message"])
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_non_stream_openai_image_api_creates_task_gallery_and_waterfall_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="sync-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "model": "gpt-image-2",
                        "prompt": "sync tracked image",
                        "n": 1,
                        "size": "1:1",
                        "response_format": "b64_json",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertIsNotNone(fake_chatgpt_service.last_image_generation)
                tracked_request_id = fake_chatgpt_service.last_image_generation["request_id"]
                self.assertTrue(tracked_request_id)

                jobs_response = client.get(
                    "/api/async/jobs?type=images.generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                jobs_payload = jobs_response.json()
                self.assertEqual(jobs_payload["total"], 1)
                self.assertEqual(jobs_payload["items"][0]["id"], tracked_request_id)
                self.assertEqual(jobs_payload["items"][0]["status"], "succeeded")

                gallery_response = client.get("/api/gallery", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 1)

                wall_response = client.get("/api/gallery/wall", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(wall_response.status_code, 200)
                self.assertEqual(wall_response.json()["total"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_image_job_streams_partial_results_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="partial-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _PartialImageChatGPTService()
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "type": "images.generations",
                        "payload": {"model": "gpt-image-2", "prompt": "partial image", "n": 2},
                    },
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                with client.stream(
                    "GET",
                    f"/api/async/jobs/{job_id}/events?ping_interval=1",
                    headers={"Authorization": f"Bearer {client_key}"},
                ) as stream_response:
                    self.assertEqual(stream_response.status_code, 200)
                    events = []
                    for event_name, payload in self._iter_sse_events(stream_response):
                        events.append((event_name, payload))
                        if event_name == "partial_result":
                            result = payload["result"]
                            self.assertEqual(len(result["data"]), 1)
                            self.assertEqual(result["data"][0]["b64_json"], "Zmlyc3Q=")
                            fake_chatgpt_service.release_second.set()
                        if event_name == "done":
                            break

                result_events = [payload for event_name, payload in events if event_name == "result"]
                self.assertTrue(result_events)
                self.assertEqual(len(result_events[-1]["result"]["data"]), 2)
                self.assertTrue(any(event_name == "partial_result" for event_name, _ in events))
            finally:
                fake_chatgpt_service.release_second.set()
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_image_job_keeps_partial_result_when_later_image_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="partial-failure-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _PartialThenFailingImageChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "type": "images.generations",
                        "payload": {"model": "gpt-image-2", "prompt": "partial then fail", "n": 2},
                    },
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                deadline = time.time() + 3
                result_response = None
                while time.time() < deadline:
                    result_response = client.get(
                        f"/api/async/jobs/{job_id}/result",
                        headers={"Authorization": f"Bearer {client_key}"},
                    )
                    if result_response.status_code == 200:
                        break
                    time.sleep(0.05)

                self.assertIsNotNone(result_response)
                assert result_response is not None
                self.assertEqual(result_response.status_code, 200)
                payload = result_response.json()
                self.assertEqual(payload["job"]["status"], "succeeded")
                self.assertEqual(payload["job"]["result_count"], 1)
                self.assertEqual(payload["result"]["data"][0]["b64_json"], "cGFydGlhbA==")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_async_image_job_failure_sse_returns_error_code_and_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="failure-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _FailingImageChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                submit_response = client.post(
                    "/api/async/jobs",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "type": "images.generations",
                        "payload": {"model": "gpt-image-2", "prompt": "fail image", "n": 1},
                    },
                )
                self.assertEqual(submit_response.status_code, 200)
                job_id = submit_response.json()["job"]["id"]

                with client.stream(
                    "GET",
                    f"/api/async/jobs/{job_id}/events?ping_interval=1",
                    headers={"Authorization": f"Bearer {client_key}"},
                ) as stream_response:
                    self.assertEqual(stream_response.status_code, 200)
                    events = list(self._iter_sse_events(stream_response))

                error_events = [payload for event_name, payload in events if event_name == "error"]
                self.assertTrue(error_events)
                self.assertEqual(error_events[-1]["error"]["code"], "image_result_not_found")
                self.assertEqual(error_events[-1]["error"]["status_code"], 502)
                self.assertIn("no downloadable image result found", error_events[-1]["error"]["message"])
                self.assertEqual(events[-1][0], "done")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_non_stream_chat_image_api_creates_task_gallery_and_waterfall_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="chat-image-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "model": "gpt-image-2",
                        "messages": [{"role": "user", "content": "draw from chat"}],
                    },
                )

                self.assertEqual(response.status_code, 200)

                jobs_response = client.get(
                    "/api/async/jobs?type=chat.completions",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                self.assertEqual(jobs_response.json()["total"], 1)

                gallery_response = client.get("/api/gallery", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 1)

                wall_response = client.get("/api/gallery/wall", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(wall_response.status_code, 200)
                self.assertEqual(wall_response.json()["total"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_stream_chat_image_api_creates_task_gallery_and_waterfall_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="chat-stream-image-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            old_ai_account_service = ai_module.account_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                ai_module.account_service = _AvailableAccountService()
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "model": "gpt-image-2",
                        "stream": True,
                        "messages": [{"role": "user", "content": "draw from chat stream"}],
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("data: [DONE]", response.text)
                self.assertIn("job_id", response.text)

                jobs_response = client.get(
                    "/api/async/jobs?type=chat.completions",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                jobs_payload = jobs_response.json()
                self.assertEqual(jobs_payload["total"], 1)
                self.assertEqual(jobs_payload["items"][0]["status"], "succeeded")
                self.assertEqual(jobs_payload["items"][0]["result_count"], 1)

                gallery_response = client.get("/api/gallery", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 1)

                wall_response = client.get("/api/gallery/wall", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(wall_response.status_code, 200)
                self.assertEqual(wall_response.json()["total"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                ai_module.account_service = old_ai_account_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_responses_compat_tracking_only_applies_to_image_generation_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                text_tool_response = client.post(
                    "/v1/responses",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={"input": "search", "tools": [{"type": "web_search"}]},
                )
                self.assertEqual(text_tool_response.status_code, 200)

                jobs_response = client.get(
                    "/api/async/jobs?type=responses",
                    headers={"Authorization": "Bearer chatgpt2api"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                self.assertEqual(jobs_response.json()["total"], 0)

                image_tool_response = client.post(
                    "/v1/responses",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={"input": "draw", "tools": [{"type": "image_generation"}]},
                )
                self.assertEqual(image_tool_response.status_code, 200)

                jobs_response = client.get(
                    "/api/async/jobs?type=responses",
                    headers={"Authorization": "Bearer chatgpt2api"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                self.assertEqual(jobs_response.json()["total"], 1)

                gallery_response = client.get("/api/gallery", headers={"Authorization": "Bearer chatgpt2api"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_stream_responses_image_api_creates_task_gallery_and_waterfall_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="responses-stream-image-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={
                        "model": "gpt-image-2",
                        "stream": True,
                        "input": "draw from responses stream",
                        "tools": [{"type": "image_generation"}],
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn("event: response.output_item.done", response.text)
                self.assertIn("data: [DONE]", response.text)
                self.assertIn("job_id", response.text)

                jobs_response = client.get(
                    "/api/async/jobs?type=responses",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                jobs_payload = jobs_response.json()
                self.assertEqual(jobs_payload["total"], 1)
                self.assertEqual(jobs_payload["items"][0]["status"], "succeeded")
                self.assertEqual(jobs_payload["items"][0]["result_count"], 1)

                gallery_response = client.get("/api/gallery", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 1)

                wall_response = client.get("/api/gallery/wall", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(wall_response.status_code, 200)
                self.assertEqual(wall_response.json()["total"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)

    def test_openai_image_api_tracking_visibility_settings_are_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="visibility-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            old_system_log_path = logger.system_log_path
            logger.set_system_log_path(Path(tmp_dir) / "system.log")
            job_service = JobService(
                Path(tmp_dir) / "jobs",
                Path(tmp_dir) / "job_results",
                fake_chatgpt_service,
                task_logs_dir=Path(tmp_dir) / "task_logs",
                max_workers=1,
            )

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            old_config_data = dict(ai_module.config.data)
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                ai_module.config.data.update(
                    {
                        "openai_compat_image_task_tracking_enabled": False,
                        "openai_compat_image_gallery_enabled": False,
                        "openai_compat_image_waterfall_enabled": True,
                    }
                )
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                    json={"model": "gpt-image-2", "prompt": "wall only", "n": 1},
                )
                self.assertEqual(response.status_code, 200)

                jobs_response = client.get(
                    "/api/async/jobs?type=images.generations",
                    headers={"Authorization": f"Bearer {client_key}"},
                )
                self.assertEqual(jobs_response.status_code, 200)
                self.assertEqual(jobs_response.json()["total"], 0)

                gallery_response = client.get("/api/gallery", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(gallery_response.status_code, 200)
                self.assertEqual(gallery_response.json()["total"], 0)

                wall_response = client.get("/api/gallery/wall", headers={"Authorization": f"Bearer {client_key}"})
                self.assertEqual(wall_response.status_code, 200)
                self.assertEqual(wall_response.json()["total"], 1)
            finally:
                ai_module.config.data = old_config_data
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)
                logger.set_system_log_path(old_system_log_path)


if __name__ == "__main__":
    unittest.main()
