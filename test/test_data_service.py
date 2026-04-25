from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image

import services.data_service as data_service_module


class DataServiceTests(unittest.TestCase):
    def test_save_image_bytes_writes_thumbnail_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_data_dir = data_service_module.DATA_DIR
            original_config_data = dict(data_service_module.config.data)
            data_service_module.DATA_DIR = Path(tmp_dir)
            try:
                with mock.patch.dict(
                        "os.environ",
                        {
                            "CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE": "",
                            "CHATGPT2API_IMAGE_THUMBNAIL_QUALITY": "",
                            "CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE": "",
                        },
                ):
                    data_service_module.config.data = {
                        **data_service_module.config.data,
                        "image_thumbnail_max_size": 512,
                        "image_thumbnail_quality": 85,
                        "image_wall_thumbnail_max_size": 960,
                    }
                    image = Image.new("RGB", (1600, 900), color=(12, 34, 56))
                    output_path = Path(tmp_dir) / "source.png"
                    image.save(output_path, format="PNG")
                    payload = output_path.read_bytes()

                    saved = data_service_module.save_image_bytes(
                        payload,
                        request_id="job-1",
                        image_index=1,
                        base_url=None,
                        mime_type="image/png",
                    )

                    original_path = data_service_module.DATA_DIR / saved["relative_path"]
                    thumbnail_path = data_service_module.DATA_DIR / saved["thumbnail_relative_path"]
                    self.assertTrue(original_path.is_file())
                    self.assertTrue(thumbnail_path.is_file())
                    self.assertIn("/api/view/data/", saved["url"])
                    self.assertIn("/api/view/data/", saved["thumbnail_url"])
                    self.assertIn("/api/view/data/", saved["wall_url"])
                    self.assertIn(saved["thumbnail_url"], saved["markdown"])
                    self.assertIn(saved["url"], saved["markdown"])

                    with Image.open(thumbnail_path) as thumbnail_image:
                        self.assertLessEqual(thumbnail_image.width, 512)
                        self.assertLessEqual(thumbnail_image.height, 512)
            finally:
                data_service_module.DATA_DIR = original_data_dir
                data_service_module.config.data = original_config_data

    def test_save_image_bytes_uses_configured_thumbnail_size_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_data_dir = data_service_module.DATA_DIR
            original_config_data = dict(data_service_module.config.data)
            data_service_module.DATA_DIR = Path(tmp_dir)
            try:
                with mock.patch.dict(
                        "os.environ",
                        {
                            "CHATGPT2API_IMAGE_THUMBNAIL_MAX_SIZE": "",
                            "CHATGPT2API_IMAGE_THUMBNAIL_QUALITY": "",
                            "CHATGPT2API_IMAGE_WALL_THUMBNAIL_MAX_SIZE": "",
                        },
                ):
                    data_service_module.config.data = {
                        **data_service_module.config.data,
                        "image_thumbnail_max_size": 128,
                        "image_thumbnail_quality": 73,
                        "image_wall_thumbnail_max_size": 320,
                    }
                    image = Image.new("RGB", (1600, 900), color=(12, 34, 56))
                    output_path = Path(tmp_dir) / "source.jpg"
                    image.save(output_path, format="JPEG")
                    saved = data_service_module.save_image_bytes(
                        output_path.read_bytes(),
                        request_id="job-2",
                        image_index=1,
                        base_url=None,
                        mime_type="image/jpeg",
                    )

                    thumbnail_path = data_service_module.DATA_DIR / saved["thumbnail_relative_path"]
                    wall_path = data_service_module.DATA_DIR / saved["wall_relative_path"]
                    with Image.open(thumbnail_path) as thumbnail_image:
                        self.assertLessEqual(thumbnail_image.width, 128)
                        self.assertLessEqual(thumbnail_image.height, 128)
                    with Image.open(wall_path) as wall_image:
                        self.assertLessEqual(wall_image.width, 320)
                        self.assertLessEqual(wall_image.height, 320)
                        self.assertAlmostEqual(wall_image.width / wall_image.height, 16 / 9, places=2)
                    self.assertEqual(data_service_module._thumbnail_save_options("JPEG"), {"quality": 73})
            finally:
                data_service_module.DATA_DIR = original_data_dir
                data_service_module.config.data = original_config_data


if __name__ == "__main__":
    unittest.main()
