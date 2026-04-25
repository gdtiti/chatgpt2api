from __future__ import annotations

import unittest

from curl_cffi.const import CurlHttpVersion

from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI


class _FakeResponse:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.status_code = 200
        self._payload = payload or {}
        self.text = ""

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


if __name__ == "__main__":
    unittest.main()
