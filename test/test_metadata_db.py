from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.metadata_db import MetadataDatabase


class MetadataDatabaseTests(unittest.TestCase):
    def test_gallery_and_waterfall_are_queryable_and_stateful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            database = MetadataDatabase(Path(tmp_dir) / "metadata.sqlite3")
            public_job = {
                "id": "job-1",
                "type": "images.generations",
                "status": "succeeded",
                "model": "gpt-image-2",
                "created_at": "2026-04-25T00:00:00Z",
                "updated_at": "2026-04-25T00:01:00Z",
                "api_key_id": "key-1",
                "api_key_name": "client",
                "prompt_preview": "海边日落",
                "requested_count": 1,
                "size": "16:9",
                "input_image_count": 0,
                "result_ready": True,
                "result_count": 1,
                "error": None,
            }
            preview_images = [
                {
                    "id": "image-1",
                    "src": "/api/view/data/2026-04-25/job-1-1-thumb.png",
                    "url": "/api/view/data/2026-04-25/job-1-1.png",
                    "thumbnail_url": "/api/view/data/2026-04-25/job-1-1-thumb.png",
                    "wall_url": "/api/view/data/2026-04-25/job-1-1-wall.png",
                    "relative_path": "2026-04-25/job-1-1.png",
                    "thumbnail_relative_path": "2026-04-25/job-1-1-thumb.png",
                    "wall_relative_path": "2026-04-25/job-1-1-wall.png",
                }
            ]

            database.record_async_job(public_job, payload={"prompt": "海边日落"}, preview_images=preview_images)

            jobs, jobs_total = database.list_async_jobs(is_admin=True, api_key_id="admin", query="日落")
            self.assertEqual(jobs_total, 1)
            self.assertEqual(jobs[0]["preview_images"][0]["wall_url"], preview_images[0]["wall_url"])

            gallery_jobs, gallery_total = database.list_gallery_jobs(is_admin=True, api_key_id="admin", query="日落")
            self.assertEqual(gallery_total, 1)
            self.assertEqual(gallery_jobs[0]["preview_images"][0]["relative_path"], "2026-04-25/job-1-1.png")

            updated = database.update_gallery_image_state(
                job_id="job-1",
                image_index=1,
                is_recommended=True,
                is_pinned=True,
                is_blocked=True,
            )
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated["wall_relative_path"], "2026-04-25/job-1-1-wall.png")
            self.assertTrue(updated["is_recommended"])
            self.assertTrue(updated["is_pinned"])
            self.assertTrue(updated["is_blocked"])

            visible_items, visible_total = database.list_waterfall_images(is_admin=True, api_key_id="admin")
            self.assertEqual(visible_total, 0)
            self.assertEqual(visible_items, [])

            all_items, all_total = database.list_waterfall_images(
                is_admin=True,
                api_key_id="admin",
                include_blocked=True,
            )
            self.assertEqual(all_total, 1)
            self.assertTrue(all_items[0]["is_blocked"])


if __name__ == "__main__":
    unittest.main()
