from __future__ import annotations

import base64
import tempfile
import threading
import time
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
