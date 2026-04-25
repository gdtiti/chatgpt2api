from __future__ import annotations

import base64
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from services.chatgpt_service import ChatGPTService, ImageGenerationError
from services.config import config


def _encode_image(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


class _FakeAccountService:
    pass


class ImageFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_config = dict(config.data)

    def tearDown(self) -> None:
        config.data = dict(self._original_config)

    def test_placeholder_strategy_returns_placeholder_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            placeholder_path = Path(tmp_dir) / "placeholder.png"
            placeholder_bytes = b"placeholder-image"
            placeholder_path.write_bytes(placeholder_bytes)
            config.data.update(
                {
                    "image_failure_strategy": "placeholder",
                    "image_placeholder_path": str(placeholder_path),
                    "image_parallel_attempts": 1,
                }
            )
            service = ChatGPTService(_FakeAccountService())
            service._call_image_generation_once = lambda *args: (_ for _ in ()).throw(
                ImageGenerationError("no downloadable image result found")
            )

            result = service.generate_with_pool("prompt", "gpt-image-2", 1)

            self.assertEqual(result["data"][0]["b64_json"], _encode_image(placeholder_bytes))

    def test_retry_strategy_retries_once_then_succeeds(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "retry",
                "image_retry_count": 1,
                "image_parallel_attempts": 1,
            }
        )
        service = ChatGPTService(_FakeAccountService())
        state = {"count": 0}

        def operation(*args):
            state["count"] += 1
            if state["count"] == 1:
                raise ImageGenerationError("no downloadable image result found")
            return {"created": 1, "data": [{"b64_json": "c3VjY2Vzcw==", "revised_prompt": "prompt"}]}

        service._call_image_generation_once = operation
        result = service.generate_with_pool("prompt", "gpt-image-2", 1)

        self.assertEqual(state["count"], 2)
        self.assertEqual(result["data"][0]["b64_json"], "c3VjY2Vzcw==")

    def test_parallel_attempts_return_first_successful_result(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 2,
            }
        )
        service = ChatGPTService(_FakeAccountService())
        state = {"count": 0}
        lock = threading.Lock()

        def operation(*args):
            with lock:
                state["count"] += 1
                current = state["count"]
            if current == 1:
                time.sleep(0.2)
                return {"created": 1, "data": [{"b64_json": "c2xvdw==", "revised_prompt": "prompt"}]}
            time.sleep(0.05)
            return {"created": 1, "data": [{"b64_json": "ZmFzdA==", "revised_prompt": "prompt"}]}

        service._call_image_generation_once = operation
        result = service.generate_with_pool("prompt", "gpt-image-2", 1)

        self.assertEqual(result["data"][0]["b64_json"], "ZmFzdA==")

    def test_requested_n_returns_first_completed_slot_without_waiting_for_slower_slot(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 1,
            }
        )
        service = ChatGPTService(_FakeAccountService())
        state = {"count": 0}
        lock = threading.Lock()

        def operation(*args):
            with lock:
                state["count"] += 1
                current = state["count"]
            if current == 1:
                time.sleep(0.25)
                return {"created": 1, "data": [{"b64_json": "c2xvdw==", "revised_prompt": "prompt"}]}
            time.sleep(0.05)
            return {"created": 1, "data": [{"b64_json": "ZmFzdA==", "revised_prompt": "prompt"}]}

        service._call_image_generation_once = operation
        started_at = time.perf_counter()
        result = service.generate_with_pool("prompt", "gpt-image-2", 2)
        elapsed = time.perf_counter() - started_at

        self.assertEqual(result["data"][0]["b64_json"], "ZmFzdA==")
        self.assertLess(elapsed, 1.0)

    def test_url_response_format_returns_relative_view_path_when_base_url_not_set(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 1,
                "image_response_format": "url",
                "base_url": "",
            }
        )
        service = ChatGPTService(_FakeAccountService())

        def operation(prompt, _model, _size, response_format, base_url, request_id, image_index):
            return service._format_image_result(
                {
                    "created": 1,
                    "data": [{"b64_json": _encode_image(b"fake-image"), "revised_prompt": prompt}],
                },
                prompt,
                response_format,
                base_url,
                request_id=request_id,
                image_index=image_index,
            )

        service._call_image_generation_once = operation

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("services.data_service.DATA_DIR", Path(tmp_dir)):
                result = service.generate_with_pool("prompt", "gpt-image-2", 1, response_format=None, request_id="task-123")

        self.assertTrue(result["data"][0]["url"].startswith("/api/view/data/"))
        self.assertIn("task-123-1", result["data"][0]["url"])

    def test_url_response_format_prefixes_base_url_when_configured(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 1,
                "image_response_format": "url",
                "base_url": "https://img.example.com/",
            }
        )
        service = ChatGPTService(_FakeAccountService())

        def operation(prompt, _model, _size, response_format, base_url, request_id, image_index):
            return service._format_image_result(
                {
                    "created": 1,
                    "data": [{"b64_json": _encode_image(b"fake-image"), "revised_prompt": prompt}],
                },
                prompt,
                response_format,
                base_url,
                request_id=request_id,
                image_index=image_index,
            )

        service._call_image_generation_once = operation

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("services.data_service.DATA_DIR", Path(tmp_dir)):
                result = service.generate_with_pool("prompt", "gpt-image-2", 1, response_format=None, request_id="task-456")

        self.assertTrue(result["data"][0]["url"].startswith("https://img.example.com/api/view/data/"))


if __name__ == "__main__":
    unittest.main()
