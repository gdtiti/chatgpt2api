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
            original_image_data_dir = data_service_module.IMAGE_DATA_DIR
            original_config_data = dict(data_service_module.config.data)
            data_service_module.DATA_DIR = Path(tmp_dir)
            data_service_module.IMAGE_DATA_DIR = Path(tmp_dir) / "images"
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

                    original_path = data_service_module.IMAGE_DATA_DIR / saved["relative_path"]
                    thumbnail_path = data_service_module.IMAGE_DATA_DIR / saved["thumbnail_relative_path"]
                    self.assertTrue(original_path.is_file())
                    self.assertTrue(thumbnail_path.is_file())
                    self.assertEqual(original_path.parent.parent, data_service_module.IMAGE_DATA_DIR)
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
                data_service_module.IMAGE_DATA_DIR = original_image_data_dir
                data_service_module.config.data = original_config_data

    def test_save_image_bytes_uses_configured_thumbnail_size_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_data_dir = data_service_module.DATA_DIR
            original_image_data_dir = data_service_module.IMAGE_DATA_DIR
            original_config_data = dict(data_service_module.config.data)
            data_service_module.DATA_DIR = Path(tmp_dir)
            data_service_module.IMAGE_DATA_DIR = Path(tmp_dir) / "images"
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

                    thumbnail_path = data_service_module.IMAGE_DATA_DIR / saved["thumbnail_relative_path"]
                    wall_path = data_service_module.IMAGE_DATA_DIR / saved["wall_relative_path"]
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
                data_service_module.IMAGE_DATA_DIR = original_image_data_dir
                data_service_module.config.data = original_config_data

    def test_resolve_image_path_reads_new_storage_before_legacy_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_data_dir = data_service_module.DATA_DIR
            original_image_data_dir = data_service_module.IMAGE_DATA_DIR
            data_service_module.DATA_DIR = Path(tmp_dir)
            data_service_module.IMAGE_DATA_DIR = Path(tmp_dir) / "images"
            try:
                date_segment = "2026-04-25"
                new_path = data_service_module.IMAGE_DATA_DIR / date_segment / "job-1.png"
                legacy_path = data_service_module.DATA_DIR / date_segment / "job-1.png"
                new_path.parent.mkdir(parents=True)
                legacy_path.parent.mkdir(parents=True)
                new_path.write_bytes(b"new")
                legacy_path.write_bytes(b"old")

                self.assertEqual(data_service_module.resolve_image_path(date_segment, "job-1.png"), new_path)

                new_path.unlink()
                self.assertEqual(data_service_module.resolve_image_path(date_segment, "job-1.png"), legacy_path)
            finally:
                data_service_module.DATA_DIR = original_data_dir
                data_service_module.IMAGE_DATA_DIR = original_image_data_dir

    def test_build_image_url_supports_template_prefix_base_url_and_relative_fallback(self) -> None:
        original_config_data = dict(data_service_module.config.data)
        try:
            with mock.patch.dict(
                    "os.environ",
                    {
                        "CHATGPT2API_BASE_URL": "",
                        "CHATGPT2API_IMAGE_URL_PREFIX": "",
                        "CHATGPT2API_IMAGE_URL_TEMPLATE": "",
                    },
            ):
                data_service_module.config.data = {
                    **data_service_module.config.data,
                    "base_url": "",
                    "image_url_prefix": "",
                    "image_url_template": "",
                }
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "/api/view/data/2026-04-25/job-1.png",
                )

                data_service_module.config.data["base_url"] = "https://api.example.com/"
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "https://api.example.com/api/view/data/2026-04-25/job-1.png",
                )

                data_service_module.config.data["image_url_prefix"] = "https://cdn.example.com/resolve/"
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "https://cdn.example.com/resolve/2026-04-25/job-1.png",
                )

                data_service_module.config.data["image_url_template"] = "https://cdn.example.com/files/{path}"
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "https://cdn.example.com/files/2026-04-25/job-1.png",
                )
        finally:
            data_service_module.config.data = original_config_data

    def test_build_image_url_supports_hf_dataset_backend(self) -> None:
        original_config_data = dict(data_service_module.config.data)
        try:
            with mock.patch.dict(
                    "os.environ",
                    {
                        "CHATGPT2API_IMAGE_URL_PREFIX": "",
                        "CHATGPT2API_IMAGE_URL_TEMPLATE": "",
                        "CHATGPT2API_IMAGE_HF_DATASET_URL": "",
                        "CHATGPT2API_IMAGE_HF_DATASET_REPO": "",
                        "CHATGPT2API_IMAGE_HF_DATASET_PATH": "",
                    },
            ):
                data_service_module.config.data = {
                    **data_service_module.config.data,
                    "image_storage_backend": "hf_datasets",
                    "image_hf_dataset_repo": "demo-owner/demo-dataset",
                    "image_hf_dataset_path": "images/generated",
                    "image_hf_dataset_url": "",
                    "image_url_prefix": "",
                    "image_url_template": "",
                }
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "https://huggingface.co/datasets/demo-owner/demo-dataset/resolve/main/images/generated/2026-04-25/job-1.png",
                )

                data_service_module.config.data["image_hf_dataset_url"] = "https://cdn.example.com/hf-images/"
                self.assertEqual(
                    data_service_module.build_image_url("2026-04-25", "job-1.png"),
                    "https://cdn.example.com/hf-images/images/generated/2026-04-25/job-1.png",
                )
        finally:
            data_service_module.config.data = original_config_data

    def test_save_image_bytes_uploads_all_renditions_to_hf_dataset(self) -> None:
        original_config_data = dict(data_service_module.config.data)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                image = Image.new("RGB", (800, 600), color=(12, 34, 56))
                output_path = Path(tmp_dir) / "source.png"
                image.save(output_path, format="PNG")
                uploads: list[tuple[str, bytes, str]] = []

                def fake_upload(relative_path: str, payload: bytes, *, commit_message: str) -> None:
                    uploads.append((relative_path, payload, commit_message))

                data_service_module.config.data = {
                    **data_service_module.config.data,
                    "image_storage_backend": "hf_datasets",
                    "image_hf_dataset_repo": "demo-owner/demo-dataset",
                    "image_hf_dataset_path": "images/generated",
                    "image_hf_dataset_url": "https://cdn.example.com/hf-images",
                }

                with mock.patch.object(data_service_module, "_upload_hf_dataset_file", side_effect=fake_upload):
                    saved = data_service_module.save_image_bytes(
                        output_path.read_bytes(),
                        request_id="job-hf",
                        image_index=2,
                        base_url=None,
                        mime_type="image/png",
                    )

                self.assertEqual(len(uploads), 3)
                self.assertEqual(uploads[0][0], saved["relative_path"])
                self.assertEqual(uploads[1][0], saved["thumbnail_relative_path"])
                self.assertEqual(uploads[2][0], saved["wall_relative_path"])
                self.assertEqual(
                    saved["url"],
                    f"https://cdn.example.com/hf-images/images/generated/{saved['relative_path']}",
                )
                self.assertEqual(
                    saved["thumbnail_url"],
                    f"https://cdn.example.com/hf-images/images/generated/{saved['thumbnail_relative_path']}",
                )
                self.assertEqual(
                    saved["wall_url"],
                    f"https://cdn.example.com/hf-images/images/generated/{saved['wall_relative_path']}",
                )
        finally:
            data_service_module.config.data = original_config_data


if __name__ == "__main__":
    unittest.main()
