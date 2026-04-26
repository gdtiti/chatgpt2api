from __future__ import annotations

import unittest

from curl_cffi.const import CurlHttpVersion

from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI


class _FakeResponse:
    def __init__(
            self,
            payload: dict[str, object] | None = None,
            *,
            status_code: int = 200,
            content: bytes = b"",
            text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = text

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.headers: dict[str, str] = {}

    def request(self, method: str, url: str, **kwargs):
        self.calls.append({
            "method": method,
            "url": url,
            **kwargs,
        })
        if url.endswith("/prepare"):
            return _FakeResponse({"conduit_token": "token-123"})
        if "/conversation/" in url:
            return _FakeResponse({"mapping": {}})
        return _FakeResponse()


class OpenAIBackendApiImageTransportTests(unittest.TestCase):
    def _build_api(self) -> tuple[OpenAIBackendAPI, _FakeSession]:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        api.base_url = "https://chatgpt.com"
        api.client_version = ""
        api.client_build_number = ""
        api.access_token = "token"
        api.fp = {}
        api.user_agent = "ua"
        api.device_id = "device"
        api.session_id = "session"
        api.pow_script_sources = []
        api.pow_data_build = ""
        api.session = _FakeSession()
        return api, api.session

    def test_prepare_image_conversation_forces_http11(self) -> None:
        api, session = self._build_api()

        conduit_token = api._prepare_image_conversation(
            "prompt",
            ChatRequirements(token="sentinel-token"),
            "gpt-image-2",
        )

        self.assertEqual(conduit_token, "token-123")
        self.assertEqual(session.calls[0]["http_version"], CurlHttpVersion.V1_1)
        self.assertEqual(session.calls[0]["method"], "POST")

    def test_get_conversation_forces_http11(self) -> None:
        api, session = self._build_api()

        api._get_conversation("conversation-id")

        self.assertEqual(session.calls[0]["http_version"], CurlHttpVersion.V1_1)
        self.assertEqual(session.calls[0]["method"], "GET")

    def test_image_prompt_distinguishes_pixel_size_from_ratio(self) -> None:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)

        prompt = api._build_image_prompt("draw a cat", "1536x1024", "high")

        self.assertIn("1536x1024", prompt)
        self.assertIn("高质量", prompt)
        self.assertNotIn("宽高比为 1536x1024", prompt)

    def test_codex_image_tool_includes_size_and_normalized_quality(self) -> None:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        captured: dict[str, object] = {}

        def fake_responses(**kwargs):
            captured.update(kwargs)
            return []

        api.responses = fake_responses  # type: ignore[method-assign]

        api._collect_codex_events("draw a cat", size="1024x1024", quality="hd")

        tools = captured["tools"]
        self.assertIsInstance(tools, list)
        tool = tools[0]
        self.assertEqual(tool["type"], "image_generation")
        self.assertEqual(tool["output_format"], "png")
        self.assertEqual(tool["size"], "1024x1024")
        self.assertEqual(tool["quality"], "high")

    def test_extract_image_tool_records_reads_assistant_asset_metadata(self) -> None:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        data = {
            "mapping": {
                "user-input": {
                    "message": {
                        "author": {"role": "user"},
                        "create_time": 1,
                        "content": {"parts": [{"asset_pointer": "file-service://file_upload"}]},
                    },
                },
                "assistant-output": {
                    "message": {
                        "author": {"role": "assistant"},
                        "create_time": 2,
                        "metadata": {"attachments": [{"asset_pointer": "file-service://file_result123"}]},
                        "content": {"parts": ["generated sediment://sed_result456"]},
                    },
                },
            },
        }

        records = api._extract_image_tool_records(data)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["file_ids"], ["file_result123"])
        self.assertEqual(records[0]["sediment_ids"], ["sed_result456"])

    def test_image_response_skips_failed_download_when_other_images_succeed(self) -> None:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)

        def fake_image_request(_method: str, url: str, **_kwargs):
            if url.endswith("/bad.png"):
                return _FakeResponse(status_code=503, text="temporarily unavailable")
            return _FakeResponse(content=b"image-bytes")

        api._image_request = fake_image_request  # type: ignore[method-assign]

        result = api._image_response(["https://example.com/bad.png", "https://example.com/good.png"], "b64_json")

        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["b64_json"], "aW1hZ2UtYnl0ZXM=")

    def test_image_response_raises_when_all_downloads_fail(self) -> None:
        api = OpenAIBackendAPI.__new__(OpenAIBackendAPI)

        def fake_image_request(_method: str, _url: str, **_kwargs):
            return _FakeResponse(status_code=503, text="temporarily unavailable")

        api._image_request = fake_image_request  # type: ignore[method-assign]

        with self.assertRaisesRegex(RuntimeError, "image_download failed"):
            api._image_response(["https://example.com/bad.png"], "b64_json")


if __name__ == "__main__":
    unittest.main()
