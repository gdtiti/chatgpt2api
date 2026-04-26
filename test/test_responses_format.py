from __future__ import annotations

import unittest

from services.chatgpt_service import ChatGPTService


class _URLImageResponseService(ChatGPTService):
    def __init__(self) -> None:
        pass

    def generate_with_pool(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
        quality: str | None = None,
    ) -> dict[str, object]:
        return {
            "created": 1777109592,
            "data": [
                {
                    "url": "/api/view/data/2026-04-25/job-1.png",
                    "thumbnail_url": "/api/view/data/2026-04-25/job-1-thumb.png",
                    "markdown": "[![image](/api/view/data/2026-04-25/job-1-thumb.png)](/api/view/data/2026-04-25/job-1.png)",
                    "revised_prompt": prompt,
                }
            ],
        }

    def stream_image_generation(
        self,
        prompt: str,
        model: str,
        n: int,
        size: str | None = None,
        response_format: str | None = "b64_json",
        base_url: str | None = None,
        request_id: str | None = None,
        quality: str | None = None,
    ):
        yield self.generate_with_pool(prompt, model, n, size, response_format, base_url, request_id, quality)


class ResponsesFormatTests(unittest.TestCase):
    def test_url_image_response_uses_responses_shape(self) -> None:
        service = _URLImageResponseService()

        response = service.create_response(
            {
                "model": "gpt-image-2",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "为我画一只猫"}]}],
                "tools": [{"type": "image_generation"}],
            }
        )

        self.assertEqual(response["object"], "response")
        self.assertEqual(response["created_at"], 1777109592)
        self.assertNotIn("data", response)
        output = response["output"]
        self.assertIsInstance(output, list)
        self.assertEqual(output[0]["type"], "image_generation_call")
        self.assertEqual(output[0]["result"], "/api/view/data/2026-04-25/job-1.png")
        self.assertEqual(output[0]["url"], "/api/view/data/2026-04-25/job-1.png")
        self.assertEqual(output[0]["thumbnail_url"], "/api/view/data/2026-04-25/job-1-thumb.png")

    def test_url_image_stream_emits_responses_items(self) -> None:
        service = _URLImageResponseService()

        events = list(
            service.stream_response(
                {
                    "model": "gpt-image-2",
                    "input": [{"role": "user", "content": [{"type": "input_text", "text": "为我画一只猫"}]}],
                    "tools": [{"type": "image_generation"}],
                    "stream": True,
                }
            )
        )

        self.assertEqual(events[0]["type"], "response.created")
        done = next(event for event in events if event["type"] == "response.output_item.done")
        item = done["item"]
        self.assertEqual(item["type"], "image_generation_call")
        self.assertEqual(item["result"], "/api/view/data/2026-04-25/job-1.png")
        self.assertEqual(item["url"], "/api/view/data/2026-04-25/job-1.png")
        self.assertEqual(events[-1]["type"], "response.completed")


if __name__ == "__main__":
    unittest.main()
