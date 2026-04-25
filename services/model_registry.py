from __future__ import annotations

from typing import Any

from services.config import config
from utils.helper import IMAGE_MODELS

IMAGE_SIZE_OPTIONS = ["1:1", "16:9", "9:16", "4:3", "3:4"]


def _capabilities_for_model(model_id: str) -> list[str]:
    if model_id in IMAGE_MODELS:
        return [
            "images.generations",
            "images.edits",
            "chat.completions:image",
            "responses:image_generation",
            "async",
        ]
    return [
        "chat.completions",
        "responses",
        "async",
    ]


class ModelRegistry:
    def build_catalog(self, model_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_item in model_items:
            if not isinstance(raw_item, dict):
                continue
            model_id = str(raw_item.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            catalog.append(
                {
                    "id": model_id,
                    "openai_id": model_id,
                    "capabilities": _capabilities_for_model(model_id),
                    "owned_by": raw_item.get("owned_by") or "chatgpt2api",
                    "async_supported": True,
                    "image_options": {
                        "size_choices": IMAGE_SIZE_OPTIONS,
                        "default_size": "1:1",
                        "response_format_choices": ["b64_json", "url"],
                        "default_response_format": config.image_response_format,
                        "supports_custom_size": True,
                        "supports_multiple_reference_images": True,
                    } if model_id in IMAGE_MODELS else None,
                }
            )
        if "auto" not in seen:
            catalog.insert(
                0,
                {
                    "id": "auto",
                    "openai_id": "auto",
                    "capabilities": ["chat.completions", "responses", "async"],
                    "owned_by": "chatgpt2api",
                    "async_supported": True,
                    "image_options": None,
                },
            )
        return catalog


model_registry = ModelRegistry()
