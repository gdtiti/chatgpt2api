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
    def test_async_job_result_and_sse_ping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client")
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.2)
            job_service = JobService(Path(tmp_dir) / "jobs", Path(tmp_dir) / "job_results", fake_chatgpt_service, max_workers=1)

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

    def test_async_image_job_passes_size_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            created = api_key_service.create_key(name="async-client", allowed_models=["gpt-image-2"])
            client_key = created["plain_text"]
            fake_chatgpt_service = _DelayedChatGPTService(delay=0.0)
            job_service = JobService(Path(tmp_dir) / "jobs", Path(tmp_dir) / "job_results", fake_chatgpt_service, max_workers=1)

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


if __name__ == "__main__":
    unittest.main()
