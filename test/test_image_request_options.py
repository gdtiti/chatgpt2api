from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.app as app_module
import api.support as support_module
from api import create_app
from services.api_key_service import APIKeyService
from services.job_service import JobService


class _CaptureChatGPTService:
    def __init__(self) -> None:
        self.last_generation: dict[str, object] | None = None
        self.last_edit: dict[str, object] | None = None

    def list_models(self) -> dict[str, object]:
        return {
            "object": "list",
            "data": [
                {"id": "gpt-image-2", "object": "model", "owned_by": "chatgpt2api"},
            ],
        }

    def create_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "chatcmpl_test", "object": "chat.completion", "choices": []}

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "resp_test", "object": "response", "output": []}

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str = "b64_json",
        base_url: str | None = None,
    ) -> dict[str, object]:
        self.last_generation = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    def edit_with_pool(
        self,
        prompt: str,
        images,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str = "b64_json",
        base_url: str | None = None,
    ) -> dict[str, object]:
        image_items = list(images)
        self.last_edit = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": response_format,
            "base_url": base_url,
            "image_count": len(image_items),
        }
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}


class ImageRequestOptionTests(unittest.TestCase):
    def test_v1_image_generation_passes_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            client_key = api_key_service.create_key(name="image-client", allowed_models=["gpt-image-2"])["plain_text"]
            fake_chatgpt_service = _CaptureChatGPTService()
            job_service = JobService(Path(tmp_dir) / "jobs", Path(tmp_dir) / "job_results", fake_chatgpt_service, max_workers=1)

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
                        "prompt": "make image",
                        "n": 1,
                        "size": "3:4",
                        "response_format": "b64_json",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fake_chatgpt_service.last_generation["size"], "3:4")
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)

    def test_v1_image_edit_passes_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            client_key = api_key_service.create_key(name="image-client", allowed_models=["gpt-image-2"])["plain_text"]
            fake_chatgpt_service = _CaptureChatGPTService()
            job_service = JobService(Path(tmp_dir) / "jobs", Path(tmp_dir) / "job_results", fake_chatgpt_service, max_workers=1)

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                response = client.post(
                    "/v1/images/edits",
                    headers={"Authorization": f"Bearer {client_key}"},
                    data={
                        "model": "gpt-image-2",
                        "prompt": "edit image",
                        "n": "1",
                        "size": "16:9",
                        "response_format": "b64_json",
                    },
                    files={"image": ("test.png", b"fake-image", "image/png")},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fake_chatgpt_service.last_edit["size"], "16:9")
                self.assertEqual(fake_chatgpt_service.last_edit["image_count"], 1)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
