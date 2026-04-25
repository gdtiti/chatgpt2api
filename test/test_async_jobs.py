from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.app as app_module
import api.support as support_module
from api import create_app
from services.api_key_service import APIKeyService
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
        return {
            "id": "chatcmpl_async",
            "object": "chat.completion",
            "created": 1,
            "model": payload.get("model") or "auto",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}],
        }

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        time.sleep(self.delay)
        return {"id": "resp_async", "object": "response", "output": []}

    def generate_with_pool(self, prompt: str, model: str, n: int, size: str | None = None, response_format: str = "b64_json", base_url: str | None = None):
        time.sleep(self.delay)
        self.last_image_generation = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    def edit_with_pool(self, prompt: str, images, model: str, n: int, size: str | None = None, response_format: str = "b64_json", base_url: str | None = None):
        time.sleep(self.delay)
        self.last_image_edit = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "image_count": len(list(images)),
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}


class AsyncJobRouteTests(unittest.TestCase):
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

    def test_async_image_job_passes_size_option(self) -> None:
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
                            "size": "4:3",
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
                self.assertEqual(fake_chatgpt_service.last_image_generation["size"], "4:3")
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


if __name__ == "__main__":
    unittest.main()
