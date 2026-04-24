from __future__ import annotations

import base64
import unittest

from utils.helper import extract_chat_image


def _data_url(payload: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


class HelperImageInputTests(unittest.TestCase):
    def test_extract_chat_image_uses_latest_user_turn_and_keeps_multiple_images(self) -> None:
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": _data_url(b"older")},
                    ],
                },
                {
                    "role": "assistant",
                    "content": "done",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": _data_url(b"newer-1")},
                        {"type": "image_url", "image_url": {"url": _data_url(b"newer-2", "image/jpeg")}},
                    ],
                },
            ],
        }

        images = extract_chat_image(body)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0][0], b"newer-1")
        self.assertEqual(images[0][1], "image/png")
        self.assertEqual(images[1][0], b"newer-2")
        self.assertEqual(images[1][1], "image/jpeg")


if __name__ == "__main__":
    unittest.main()
