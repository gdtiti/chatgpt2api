from __future__ import annotations

import base64
import tempfile
import threading
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
        slow_started = threading.Event()
        slow_completed = threading.Event()
        release_slow = threading.Event()
        call_order: list[int] = []
        lock = threading.Lock()

        def operation(_prompt, _model, _size, _response_format, _base_url, _request_id, slot_index, _quality=None):
            with lock:
                call_order.append(slot_index)
            if slot_index == 1:
                slow_started.set()
                release_slow.wait(timeout=10.0)
                slow_completed.set()
                return {"created": 1, "data": [{"b64_json": "c2xvdw==", "revised_prompt": "prompt"}]}
            return {"created": 1, "data": [{"b64_json": "ZmFzdA==", "revised_prompt": "prompt"}]}

        service._call_image_generation_once = operation
        try:
            result = service.generate_with_pool("prompt", "gpt-image-2", 1)
            self.assertEqual(result["data"][0]["b64_json"], "ZmFzdA==")
            self.assertTrue(slow_started.wait(timeout=1.0))
            self.assertFalse(slow_completed.is_set())
            self.assertCountEqual(call_order, [1, 2])
        finally:
            release_slow.set()
            slow_completed.wait(timeout=1.0)

    def test_requested_n_returns_first_n_successes_with_one_extra_slot(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 2,
            }
        )
        service = ChatGPTService(_FakeAccountService())
        slow_started = threading.Event()
        slow_completed = threading.Event()
        release_slow = threading.Event()

        def operation(_prompt, _model, _size, _response_format, _base_url, _request_id, slot_index, _quality=None):
            if slot_index == 1:
                slow_started.set()
                release_slow.wait(timeout=10.0)
                slow_completed.set()
                return {"created": 1, "data": [{"b64_json": "c2xvdw==", "revised_prompt": "prompt"}]}
            encoded = base64.b64encode(f"slot-{slot_index}".encode("ascii")).decode("ascii")
            return {"created": 1, "data": [{"b64_json": encoded, "revised_prompt": f"prompt-{slot_index}"}]}

        service._call_image_generation_once = operation
        try:
            result = service.generate_with_pool("prompt", "gpt-image-2", 4)
            self.assertTrue(slow_started.wait(timeout=1.0))
            self.assertFalse(slow_completed.is_set())
            self.assertEqual(len(result["data"]), 4)
            self.assertCountEqual(
                [item["b64_json"] for item in result["data"]],
                [
                    base64.b64encode(b"slot-2").decode("ascii"),
                    base64.b64encode(b"slot-3").decode("ascii"),
                    base64.b64encode(b"slot-4").decode("ascii"),
                    base64.b64encode(b"slot-5").decode("ascii"),
                ],
            )
        finally:
            release_slow.set()
            slow_completed.wait(timeout=1.0)

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

        def operation(prompt, _model, _size, response_format, base_url, request_id, image_index, _quality=None):
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
        self.assertNotIn("b64_json", result["data"][0])

    def test_url_config_overrides_explicit_b64_response_format(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 1,
                "image_response_format": "url",
                "image_url_include_b64_when_requested": False,
                "base_url": "",
            }
        )
        service = ChatGPTService(_FakeAccountService())

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("services.data_service.DATA_DIR", Path(tmp_dir)):
                result = service._format_image_result(
                    {
                        "created": 1,
                        "data": [{"b64_json": _encode_image(b"fake-image"), "revised_prompt": "prompt"}],
                    },
                    "prompt",
                    "b64_json",
                    None,
                    request_id="task-override",
                    image_index=1,
                )

        self.assertTrue(result["data"][0]["url"].startswith("/api/view/data/"))
        self.assertNotIn("b64_json", result["data"][0])

    def test_url_config_can_include_b64_for_explicit_b64_request(self) -> None:
        config.data.update(
            {
                "image_failure_strategy": "fail",
                "image_parallel_attempts": 1,
                "image_response_format": "url",
                "image_url_include_b64_when_requested": True,
                "base_url": "",
            }
        )
        service = ChatGPTService(_FakeAccountService())

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("services.data_service.DATA_DIR", Path(tmp_dir)):
                result = service._format_image_result(
                    {
                        "created": 1,
                        "data": [{"b64_json": _encode_image(b"fake-image"), "revised_prompt": "prompt"}],
                    },
                    "prompt",
                    "b64_json",
                    None,
                    request_id="task-compat",
                    image_index=1,
                )

        self.assertTrue(result["data"][0]["url"].startswith("/api/view/data/"))
        self.assertEqual(result["data"][0]["b64_json"], _encode_image(b"fake-image"))

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

        def operation(prompt, _model, _size, response_format, base_url, request_id, image_index, _quality=None):
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
        self.assertNotIn("b64_json", result["data"][0])

    def test_stream_single_image_result_stops_after_first_image_result(self) -> None:
        service = ChatGPTService(_FakeAccountService())
        state = {"continued_after_result": False}

        class FakeBackend:
            def stream_image_chat_completions(self, **_kwargs):
                yield {
                    "created": 1,
                    "choices": [{
                        "delta": {"content": f"![image](data:image/png;base64,{_encode_image(b'fake-image')})"},
                        "finish_reason": None,
                    }],
                }
                state["continued_after_result"] = True
                yield {
                    "created": 1,
                    "choices": [{
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                }

        with patch.object(ChatGPTService, "_new_backend", return_value=FakeBackend()):
            chunks = list(
                service._stream_single_image_result(
                    "prompt",
                    "gpt-image-2",
                    1,
                    1,
                    "token",
                    response_format="b64_json",
                )
            )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["object"], "image.generation.result")
        self.assertFalse(state["continued_after_result"])


if __name__ == "__main__":
    unittest.main()
