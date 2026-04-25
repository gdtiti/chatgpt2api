from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import api.support as support_module
from api import create_app


class _FakeChatGPTService:
    def list_models(self) -> dict[str, object]:
        return {"object": "list", "data": []}

    def create_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "chatcmpl_test", "object": "chat.completion", "choices": []}

    def create_response(self, payload: dict[str, object]) -> dict[str, object]:
        return {"id": "resp_test", "object": "response", "output": []}


class _FakeJobService:
    def shutdown(self, wait: bool = False) -> None:
        return None


class WebFallbackRouteTests(unittest.TestCase):
    def test_exported_pages_support_get_and_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            web_dist = Path(tmp_dir)
            (web_dist / "index.html").write_text("<html>home</html>", encoding="utf-8")
            for page in ("docs", "settings", "jobs", "wall", "gallery", "image"):
                page_dir = web_dist / page
                page_dir.mkdir(parents=True)
                (page_dir / "index.html").write_text(f"<html>{page}</html>", encoding="utf-8")

            original_web_dist = support_module.WEB_DIST_DIR
            support_module.WEB_DIST_DIR = web_dist
            try:
                client = TestClient(create_app(chatgpt_service=_FakeChatGPTService(), job_service=_FakeJobService()))

                for page in ("/docs/", "/settings/", "/jobs/", "/wall/", "/gallery/", "/image/"):
                    with self.subTest(page=page, method="GET"):
                        response = client.get(page)
                        self.assertEqual(response.status_code, 200)
                    with self.subTest(page=page, method="HEAD"):
                        response = client.head(page)
                        self.assertEqual(response.status_code, 200)

                self.assertEqual(client.get("/_next/missing.js").status_code, 404)
            finally:
                support_module.WEB_DIST_DIR = original_web_dist

    def test_swagger_ui_uses_dedicated_route(self) -> None:
        client = TestClient(create_app(chatgpt_service=_FakeChatGPTService(), job_service=_FakeJobService()))

        response = client.get("/swagger")

        self.assertEqual(response.status_code, 200)
        self.assertIn("swagger-ui", response.text.lower())


if __name__ == "__main__":
    unittest.main()
