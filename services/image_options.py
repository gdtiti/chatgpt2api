from __future__ import annotations

import re


class ImageOptionError(ValueError):
    pass


IMAGE_RATIO_SIZE_OPTIONS = ["1:1", "4:3", "3:4", "3:2", "16:9", "21:9", "9:16"]
IMAGE_RESOLUTION_PRESETS: dict[str, dict[str, str]] = {
    "1:1": {"sd": "1248x1248", "2k": "2048x2048", "4k": "2880x2880"},
    "4:3": {"sd": "1440x1072", "2k": "2048x1536", "4k": "3264x2448"},
    "3:4": {"sd": "1072x1440", "2k": "1536x2048", "4k": "2448x3264"},
    "3:2": {"sd": "1536x1024", "2k": "2160x1440", "4k": "3456x2304"},
    "16:9": {"sd": "1664x928", "2k": "2560x1440", "4k": "3840x2160"},
    "21:9": {"sd": "1904x816", "2k": "3360x1440", "4k": "3808x1632"},
    "9:16": {"sd": "928x1664", "2k": "1440x2560", "4k": "2160x3840"},
}
IMAGE_QUALITY_OPTIONS = ["low", "medium", "high"]

_PIXEL_SIZE_RE = re.compile(r"^(\d+)x(\d+)$")
_RATIO_SIZE_RE = re.compile(r"^(\d+):(\d+)$")

_MAX_GENERATE_EDGE = 3840
_MAX_GENERATE_RATIO = 3
_MIN_GENERATE_PIXELS = 655_360
_MAX_GENERATE_PIXELS = 8_294_400
_MAX_FREE_GENERATE_PIXELS = 1_577_536
_SIZE_MULTIPLE = 16


def normalize_image_size(value: object) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "")
    if not text or text == "auto":
        return None
    match = _PIXEL_SIZE_RE.fullmatch(text)
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        _validate_pixel_size(width, height)
        return f"{width}x{height}"
    if "x" in text:
        raise ImageOptionError("size must use WIDTHxHEIGHT with integer pixel values")
    ratio_match = _RATIO_SIZE_RE.fullmatch(text)
    if ratio_match:
        width = int(ratio_match.group(1))
        height = int(ratio_match.group(2))
        if width <= 0 or height <= 0:
            raise ImageOptionError("size ratio values must be positive")
        if max(width, height) / min(width, height) > _MAX_GENERATE_RATIO:
            raise ImageOptionError("size ratio must not exceed 3:1")
        return f"{width}:{height}"
    return text


def is_pixel_image_size(value: object) -> bool:
    try:
        normalized = normalize_image_size(value)
    except ImageOptionError:
        return False
    return bool(normalized and _PIXEL_SIZE_RE.fullmatch(normalized))


def normalize_image_quality(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text or text == "auto":
        return None
    if text == "hd":
        return "high"
    if text == "standard":
        return "medium"
    if text not in IMAGE_QUALITY_OPTIONS:
        raise ImageOptionError("quality must be low, medium, high, hd, or standard")
    return text


def requires_paid_generate_account(value: object) -> bool:
    normalized = normalize_image_size(value)
    if not normalized or not _PIXEL_SIZE_RE.fullmatch(normalized):
        return False
    width, height = _parse_pixel_size(normalized)
    return width * height > _MAX_FREE_GENERATE_PIXELS


def _parse_pixel_size(value: str) -> tuple[int, int]:
    match = _PIXEL_SIZE_RE.fullmatch(value)
    if not match:
        raise ImageOptionError("size must use WIDTHxHEIGHT")
    return int(match.group(1)), int(match.group(2))


def _validate_pixel_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ImageOptionError("size width and height must be positive")
    if width % _SIZE_MULTIPLE != 0 or height % _SIZE_MULTIPLE != 0:
        raise ImageOptionError(f"size width and height must be multiples of {_SIZE_MULTIPLE}")
    if max(width, height) > _MAX_GENERATE_EDGE:
        raise ImageOptionError(f"size longest edge must not exceed {_MAX_GENERATE_EDGE}")
    if max(width, height) / min(width, height) > _MAX_GENERATE_RATIO:
        raise ImageOptionError("size ratio must not exceed 3:1")
    pixels = width * height
    if pixels < _MIN_GENERATE_PIXELS:
        raise ImageOptionError(f"size total pixels must be at least {_MIN_GENERATE_PIXELS}")
    if pixels > _MAX_GENERATE_PIXELS:
        raise ImageOptionError(f"size total pixels must not exceed {_MAX_GENERATE_PIXELS}")
