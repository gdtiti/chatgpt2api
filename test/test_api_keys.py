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

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
        quality: str | None = None,
    ):
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
        request_id: str | None = None,
    ):
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
                    ["1:1", "4:3", "3:4", "3:2", "16:9", "21:9", "9:16"],
                )
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)

    def test_client_login_returns_session_and_limits_are_exposed(self) -> None:
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

                created = client.post(
                    "/api/admin/keys",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={
                        "name": "test-console",
                        "allowed_models": ["gpt-image-2"],
                        "max_requests": 8,
                        "max_image_count": 5,
                    },
                )
                self.assertEqual(created.status_code, 200)
                plain_text = created.json()["plain_text"]

                login_response = client.post(
                    "/auth/login",
                    headers={"Authorization": f"Bearer {plain_text}"},
                )
                self.assertEqual(login_response.status_code, 200)
                session = login_response.json()["session"]
                self.assertEqual(session["kind"], "client")
                self.assertEqual(session["name"], "test-console")
                self.assertEqual(session["allowed_models"], ["gpt-image-2"])
                self.assertEqual(session["max_requests"], 8)
                self.assertEqual(session["remaining_requests"], 8)
                self.assertEqual(session["max_image_count"], 5)
                self.assertEqual(session["remaining_image_count"], 5)

                list_response = client.get("/api/admin/keys", headers={"Authorization": "Bearer chatgpt2api"})
                self.assertEqual(list_response.status_code, 200)
                item = list_response.json()["items"][0]
                self.assertEqual(item["max_requests"], 8)
                self.assertEqual(item["remaining_requests"], 8)
                self.assertEqual(item["max_image_count"], 5)
                self.assertEqual(item["remaining_image_count"], 5)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)

    def test_request_limit_and_image_quota_are_enforced(self) -> None:
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

                request_limited_key = client.post(
                    "/api/admin/keys",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={"name": "once-only", "max_requests": 1},
                ).json()["plain_text"]

                first_models = client.get("/v1/models", headers={"Authorization": f"Bearer {request_limited_key}"})
                self.assertEqual(first_models.status_code, 200)
                second_models = client.get("/v1/models", headers={"Authorization": f"Bearer {request_limited_key}"})
                self.assertEqual(second_models.status_code, 429)
                self.assertIn("request limit exceeded", second_models.text)

                image_limited_key = client.post(
                    "/api/admin/keys",
                    headers={"Authorization": "Bearer chatgpt2api"},
                    json={
                        "name": "image-limited",
                        "allowed_models": ["gpt-image-2"],
                        "max_image_count": 1,
                    },
                ).json()["plain_text"]

                first_image = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {image_limited_key}"},
                    json={"model": "gpt-image-2", "prompt": "one", "n": 1},
                )
                self.assertEqual(first_image.status_code, 200)
                second_image = client.post(
                    "/v1/images/generations",
                    headers={"Authorization": f"Bearer {image_limited_key}"},
                    json={"model": "gpt-image-2", "prompt": "two", "n": 1},
                )
                self.assertEqual(second_image.status_code, 429)
                self.assertIn("image quota exceeded", second_image.text)
            finally:
                support_module.api_key_service = old_support_service
                app_module.api_key_service = old_app_service
                job_service.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
