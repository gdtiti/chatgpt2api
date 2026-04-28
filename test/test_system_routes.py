from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.system import create_router
import services.data_service as data_service_module


class SystemRouteTests(unittest.TestCase):
    def test_view_image_response_is_inline_previewable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_data_dir = data_service_module.DATA_DIR
            original_image_data_dir = data_service_module.IMAGE_DATA_DIR
            data_service_module.DATA_DIR = Path(tmp_dir)
            data_service_module.IMAGE_DATA_DIR = Path(tmp_dir) / "images"
            try:
                image_dir = data_service_module.IMAGE_DATA_DIR / "2026-04-28"
                image_dir.mkdir(parents=True)
                (image_dir / "job-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")

                app = FastAPI()
                app.include_router(create_router("test"))
                client = TestClient(app)

                response = client.get("/api/view/data/2026-04-28/job-1.png")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "image/png")
                self.assertTrue(response.headers["content-disposition"].startswith("inline;"))
            finally:
                data_service_module.DATA_DIR = original_data_dir
                data_service_module.IMAGE_DATA_DIR = original_image_data_dir


if __name__ == "__main__":
    unittest.main()
