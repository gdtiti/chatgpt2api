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


class _FakeChatGPTService:
    def list_models(self) -> dict[str, object]:
        return {
            "object": "list",
            "data": [
                {"id": "auto", "object": "model", "owned_by": "chatgpt2api"},
                {"id": "gpt-image-2", "object": "model", "owned_by": "chatgpt2api"},
            ],
        }

    def create_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "chatcmpl_test", "object": "chat.completion", "choices": []}

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "resp_test", "object": "response", "output": []}

    def generate_with_pool(self, prompt: str, model: str, n: int, size: str | None = None, response_format: str = "b64_json", base_url: str | None = None):
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}

    def edit_with_pool(self, prompt: str, images, model: str, n: int, size: str | None = None, response_format: str = "b64_json", base_url: str | None = None):
        return {"created": 1, "data": [{"b64_json": "ZmFrZQ==", "revised_prompt": prompt}]}


class APIKeyRouteTests(unittest.TestCase):
    def test_admin_key_can_create_client_key_and_client_key_can_call_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            api_key_service = APIKeyService(Path(tmp_dir) / "api_keys.json", admin_key_provider=lambda: "chatgpt2api")
            fake_chatgpt_service = _FakeChatGPTService()
            job_service = JobService(Path(tmp_dir) / "jobs", Path(tmp_dir) / "job_results", fake_chatgpt_service, max_workers=1)

            old_support_service = support_module.api_key_service
            old_app_service = app_module.api_key_service
            try:
                support_module.api_key_service = api_key_service
                app_module.api_key_service = api_key_service
                client = TestClient(create_app(chatgpt_service=fake_chatgpt_service, job_service=job_service))

                create_response = client.post(
                    "/api/admin/keys",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={"name": "client-a", "allowed_models": ["gpt-image-2"]},
                )
                self.assertEqual(create_response.status_code, 200)
                created = create_response.json()
                plain_text = created["plain_text"]
                self.assertTrue(plain_text.startswith("cg2a_"))

                list_response = client.get("/api/admin/keys", headers={"Authorization": "Bearer chatgpt2api"})
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(len(list_response.json()["items"]), 1)

                models_response = client.get(
                    "/v1/models",
                    headers={"Authorization": f"Bearer {plain_text}"},
                )
                self.assertEqual(models_response.status_code, 200)
                self.assertEqual(
                    [item["id"] for item in models_response.json()["data"]],
                    ["gpt-image-2"],
                )

                catalog_response = client.get(
                    "/api/catalog/models",
                    headers={"Authorization": f"Bearer {plain_text}"},
                )
                self.assertEqual(catalog_response.status_code, 200)
                self.assertEqual(catalog_response.json()["items"][0]["id"], "auto")
                self.assertEqual(catalog_response.json()["items"][1]["id"], "gpt-image-2")
                self.assertEqual(
                    catalog_response.json()["items"][1]["image_options"]["size_choices"],
                    ["1:1", "16:9", "9:16", "4:3", "3:4"],
                )
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
