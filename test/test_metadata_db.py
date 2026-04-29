from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from services.metadata_db import MetadataDatabase


class MetadataDatabaseTests(unittest.TestCase):
    def test_quick_check_failure_during_initialize_is_quarantined_without_recursion(self) -> None:
        class QuickCheckFailOnceDatabase(MetadataDatabase):
            def __init__(self, path: Path) -> None:
                self.initialize_calls = 0
                self.verify_calls = 0
                super().__init__(path)

            def _initialize(self) -> None:
                self.initialize_calls += 1
                super()._initialize()

            def _verify_connection(self, connection: sqlite3.Connection) -> None:
                self.verify_calls += 1
                if self.verify_calls == 1:
                    raise sqlite3.DatabaseError("sqlite integrity check failed: forced")
                super()._verify_connection(connection)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "metadata.sqlite3"
            db_path.write_bytes(b"placeholder")

            database = QuickCheckFailOnceDatabase(db_path)

            self.assertEqual(database.initialize_calls, 1)
            quarantined = list(Path(tmp_dir).glob("metadata.sqlite3.corrupt-*"))
            self.assertEqual(len(quarantined), 1)
            jobs, total = database.list_async_jobs(is_admin=True, api_key_id="admin")
            self.assertEqual(total, 0)
            self.assertEqual(jobs, [])

    def test_missing_core_tables_are_recreated_on_next_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "metadata.sqlite3"
            database = MetadataDatabase(db_path)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("DROP TABLE async_jobs")
                connection.commit()
            finally:
                connection.close()

            jobs, total = database.list_async_jobs(is_admin=True, api_key_id="admin")

            self.assertEqual(total, 0)
            self.assertEqual(jobs, [])
            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'async_jobs'"
                ).fetchone()
            finally:
                connection.close()
            self.assertIsNotNone(row)

    def test_corrupt_database_is_quarantined_and_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "metadata.sqlite3"
            db_path.write_bytes(b"not a sqlite database")

            database = MetadataDatabase(db_path)
            database.record_task_log("job-1", "/tmp/job-1.log")

            quarantined = list(Path(tmp_dir).glob("metadata.sqlite3.corrupt-*"))
            self.assertEqual(len(quarantined), 1)
            jobs, total = database.list_async_jobs(is_admin=True, api_key_id="admin")
            self.assertEqual(total, 0)
            self.assertEqual(jobs, [])

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

            result_payload = {"result": {"created": 1, "data": [{"url": preview_images[0]["url"]}]}}
            database.record_async_job(
                public_job,
                payload={"prompt": "海边日落"},
                preview_images=preview_images,
                result=result_payload,
            )

            self.assertTrue(database.has_async_jobs(is_admin=True, api_key_id="admin"))
            self.assertTrue(database.has_async_jobs(is_admin=False, api_key_id="key-1"))
            self.assertFalse(database.has_async_jobs(is_admin=False, api_key_id="missing-key"))

            record = database.get_async_job_record("job-1", is_admin=False, api_key_id="key-1")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record["payload"], {"prompt": "海边日落"})
            self.assertEqual(record["result"], result_payload)

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

    def test_task_gallery_and_waterfall_visibility_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            database = MetadataDatabase(Path(tmp_dir) / "metadata.sqlite3")
            public_job = {
                "id": "job-hidden-task",
                "type": "images.generations",
                "status": "succeeded",
                "model": "gpt-image-2",
                "created_at": "2026-04-25T00:00:00Z",
                "updated_at": "2026-04-25T00:01:00Z",
                "api_key_id": "key-1",
                "api_key_name": "client",
                "prompt_preview": "隐藏任务",
                "requested_count": 1,
                "size": "1:1",
                "input_image_count": 0,
                "result_ready": True,
                "result_count": 1,
                "error": None,
            }
            preview_images = [
                {
                    "id": "image-1",
                    "src": "/api/view/data/2026-04-25/job-hidden-task-1-thumb.png",
                    "url": "/api/view/data/2026-04-25/job-hidden-task-1.png",
                    "thumbnail_url": "/api/view/data/2026-04-25/job-hidden-task-1-thumb.png",
                }
            ]

            database.record_async_job(
                public_job,
                payload={"prompt": "隐藏任务"},
                preview_images=preview_images,
                include_task_tracking=False,
                include_gallery=False,
                include_waterfall=True,
            )

            jobs, jobs_total = database.list_async_jobs(is_admin=True, api_key_id="admin")
            self.assertEqual(jobs_total, 0)
            self.assertEqual(jobs, [])

            gallery_jobs, gallery_total = database.list_gallery_jobs(is_admin=True, api_key_id="admin")
            self.assertEqual(gallery_total, 0)
            self.assertEqual(gallery_jobs, [])

            wall_items, wall_total = database.list_waterfall_images(is_admin=True, api_key_id="admin")
            self.assertEqual(wall_total, 1)
            self.assertEqual(wall_items[0]["job_id"], "job-hidden-task")


if __name__ == "__main__":
    unittest.main()
