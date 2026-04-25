from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
from threading import Lock
from typing import Callable
from uuid import uuid4

from services.config import config

_UNSET = object()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _clean_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return cleaned


def _parse_datetime(value: object) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_expired(expires_at: object) -> bool:
    parsed = _parse_datetime(expires_at)
    return parsed is not None and parsed <= datetime.now(timezone.utc)


def _clean_optional_limit(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _remaining_limit(max_value: int | None, current: int) -> int | None:
    if max_value is None:
        return None
    return max(0, max_value - max(0, current))


class APIKeyAuthError(Exception):
    def __init__(self, message: str, *, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AuthPrincipal:
    key_id: str
    name: str
    kind: str
    scopes: tuple[str, ...]
    allowed_models: tuple[str, ...]
    request_count: int = 0
    max_requests: int | None = None
    image_count: int = 0
    max_image_count: int | None = None
    is_admin: bool = False

    def allows_model(self, model: str) -> bool:
        model_id = _clean_text(model) or "auto"
        return self.is_admin or not self.allowed_models or model_id in self.allowed_models

    @property
    def remaining_requests(self) -> int | None:
        return _remaining_limit(self.max_requests, self.request_count)

    @property
    def remaining_image_count(self) -> int | None:
        return _remaining_limit(self.max_image_count, self.image_count)


class APIKeyService:
    def __init__(self, store_file: Path, admin_key_provider: Callable[[], str] | None = None):
        self.store_file = store_file
        self._admin_key_provider = admin_key_provider or (lambda: config.auth_key)
        self._lock = Lock()
        self._items = self._load_items()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _normalize_item(self, item: object) -> dict[str, object] | None:
        if not isinstance(item, dict):
            return None
        key_hash = _clean_text(item.get("key_hash"))
        if not key_hash:
            return None
        key_id = _clean_text(item.get("id")) or uuid4().hex[:12]
        created_at = _clean_text(item.get("created_at")) or _utc_now()
        updated_at = _clean_text(item.get("updated_at")) or created_at
        return {
            "id": key_id,
            "name": _clean_text(item.get("name")) or f"key-{key_id[:6]}",
            "prefix": _clean_text(item.get("prefix")),
            "key_hash": key_hash,
            "enabled": bool(item.get("enabled", True)),
            "scopes": _clean_list(item.get("scopes")) or ["inference"],
            "allowed_models": _clean_list(item.get("allowed_models")),
            "created_at": created_at,
            "updated_at": updated_at,
            "last_used_at": _clean_text(item.get("last_used_at")) or None,
            "expires_at": _clean_text(item.get("expires_at")) or None,
            "request_count": max(0, int(item.get("request_count") or 0)),
            "max_requests": _clean_optional_limit(item.get("max_requests")),
            "image_count": max(0, int(item.get("image_count") or 0)),
            "max_image_count": _clean_optional_limit(item.get("max_image_count")),
        }

    def _load_items(self) -> list[dict[str, object]]:
        if not self.store_file.exists():
            return []
        try:
            data = json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [normalized for item in data if (normalized := self._normalize_item(item)) is not None]

    def _save_items(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self.store_file.write_text(json.dumps(self._items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _public_item(item: dict[str, object]) -> dict[str, object]:
        request_count = max(0, int(item.get("request_count") or 0))
        max_requests = _clean_optional_limit(item.get("max_requests"))
        image_count = max(0, int(item.get("image_count") or 0))
        max_image_count = _clean_optional_limit(item.get("max_image_count"))
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "prefix": item.get("prefix"),
            "enabled": bool(item.get("enabled")),
            "scopes": list(item.get("scopes") or []),
            "allowed_models": list(item.get("allowed_models") or []),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "last_used_at": item.get("last_used_at"),
            "expires_at": item.get("expires_at"),
            "request_count": request_count,
            "max_requests": max_requests,
            "remaining_requests": _remaining_limit(max_requests, request_count),
            "image_count": image_count,
            "max_image_count": max_image_count,
            "remaining_image_count": _remaining_limit(max_image_count, image_count),
        }

    @staticmethod
    def _principal_from_item(item: dict[str, object]) -> AuthPrincipal:
        return AuthPrincipal(
            key_id=str(item.get("id")),
            name=str(item.get("name") or "client"),
            kind="client",
            scopes=tuple(_clean_list(item.get("scopes")) or ["inference"]),
            allowed_models=tuple(_clean_list(item.get("allowed_models"))),
            request_count=max(0, int(item.get("request_count") or 0)),
            max_requests=_clean_optional_limit(item.get("max_requests")),
            image_count=max(0, int(item.get("image_count") or 0)),
            max_image_count=_clean_optional_limit(item.get("max_image_count")),
            is_admin=False,
        )

    @staticmethod
    def _admin_principal() -> AuthPrincipal:
        return AuthPrincipal(
            key_id="admin",
            name="admin",
            kind="admin",
            scopes=("admin", "inference"),
            allowed_models=(),
            is_admin=True,
        )

    @staticmethod
    def session_payload(principal: AuthPrincipal) -> dict[str, object]:
        return {
            "key_id": principal.key_id,
            "name": principal.name,
            "kind": principal.kind,
            "is_admin": principal.is_admin,
            "scopes": list(principal.scopes),
            "allowed_models": list(principal.allowed_models),
            "request_count": principal.request_count,
            "max_requests": principal.max_requests,
            "remaining_requests": principal.remaining_requests,
            "image_count": principal.image_count,
            "max_image_count": principal.max_image_count,
            "remaining_image_count": principal.remaining_image_count,
        }

    @staticmethod
    def _validate_item(item: dict[str, object], *, strict: bool = False) -> bool:
        if not bool(item.get("enabled")):
            if strict:
                raise APIKeyAuthError("api key is disabled")
            return False
        if _is_expired(item.get("expires_at")):
            if strict:
                raise APIKeyAuthError("api key is expired")
            return False
        max_requests = _clean_optional_limit(item.get("max_requests"))
        request_count = max(0, int(item.get("request_count") or 0))
        if strict and max_requests is not None and request_count >= max_requests:
            raise APIKeyAuthError("api key request limit exceeded", status_code=429)
        return True

    def list_keys(self) -> list[dict[str, object]]:
        with self._lock:
            return [self._public_item(item) for item in self._items]

    def create_key(
            self,
            *,
            name: str,
            allowed_models: list[str] | None = None,
            scopes: list[str] | None = None,
            expires_at: str | None = None,
            max_requests: int | None = None,
            max_image_count: int | None = None,
    ) -> dict[str, object]:
        plain_text = f"cg2a_{secrets.token_urlsafe(24)}"
        key_id = uuid4().hex[:12]
        now = _utc_now()
        item = {
            "id": key_id,
            "name": _clean_text(name) or f"key-{key_id[:6]}",
            "prefix": plain_text[:12],
            "key_hash": self._hash_token(plain_text),
            "enabled": True,
            "scopes": _clean_list(scopes) or ["inference"],
            "allowed_models": _clean_list(allowed_models),
            "created_at": now,
            "updated_at": now,
            "last_used_at": None,
            "expires_at": _clean_text(expires_at) or None,
            "request_count": 0,
            "max_requests": _clean_optional_limit(max_requests),
            "image_count": 0,
            "max_image_count": _clean_optional_limit(max_image_count),
        }
        with self._lock:
            self._items.append(item)
            self._save_items()
        return {
            "item": self._public_item(item),
            "plain_text": plain_text,
        }

    def update_key(
            self,
            key_id: str,
            *,
            name: str | None | object = _UNSET,
            enabled: bool | None | object = _UNSET,
            allowed_models: list[str] | None | object = _UNSET,
            scopes: list[str] | None | object = _UNSET,
            expires_at: str | None | object = _UNSET,
            max_requests: int | None | object = _UNSET,
            max_image_count: int | None | object = _UNSET,
    ) -> dict[str, object] | None:
        normalized_key_id = _clean_text(key_id)
        with self._lock:
            for index, item in enumerate(self._items):
                if item.get("id") != normalized_key_id:
                    continue
                next_item = dict(item)
                if name is not _UNSET:
                    next_item["name"] = _clean_text(name) or next_item["name"]
                if enabled is not _UNSET:
                    next_item["enabled"] = bool(enabled)
                if allowed_models is not _UNSET:
                    next_item["allowed_models"] = _clean_list(allowed_models)
                if scopes is not _UNSET:
                    next_item["scopes"] = _clean_list(scopes) or ["inference"]
                if expires_at is not _UNSET:
                    next_item["expires_at"] = _clean_text(expires_at) or None
                if max_requests is not _UNSET:
                    next_item["max_requests"] = _clean_optional_limit(max_requests)
                if max_image_count is not _UNSET:
                    next_item["max_image_count"] = _clean_optional_limit(max_image_count)
                next_item["updated_at"] = _utc_now()
                self._items[index] = next_item
                self._save_items()
                return self._public_item(next_item)
        return None

    def rotate_key(self, key_id: str) -> dict[str, object] | None:
        normalized_key_id = _clean_text(key_id)
        plain_text = f"cg2a_{secrets.token_urlsafe(24)}"
        with self._lock:
            for index, item in enumerate(self._items):
                if item.get("id") != normalized_key_id:
                    continue
                next_item = dict(item)
                next_item["prefix"] = plain_text[:12]
                next_item["key_hash"] = self._hash_token(plain_text)
                next_item["updated_at"] = _utc_now()
                next_item["last_used_at"] = None
                self._items[index] = next_item
                self._save_items()
                return {
                    "item": self._public_item(next_item),
                    "plain_text": plain_text,
                }
        return None

    def delete_key(self, key_id: str) -> bool:
        normalized_key_id = _clean_text(key_id)
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.get("id") != normalized_key_id]
            changed = len(self._items) != before
            if changed:
                self._save_items()
            return changed

    def peek_principal(
            self,
            token: str,
            *,
            allow_admin: bool = True,
            strict: bool = False,
    ) -> AuthPrincipal | None:
        normalized = _clean_text(token)
        if not normalized:
            return None
        admin_key = _clean_text(self._admin_key_provider())
        if allow_admin and admin_key and normalized == admin_key:
            return self._admin_principal()
        token_hash = self._hash_token(normalized)
        with self._lock:
            for item in self._items:
                if item.get("key_hash") != token_hash:
                    continue
                if not self._validate_item(item, strict=strict):
                    return None
                return self._principal_from_item(item)
        return None

    def authenticate(self, token: str, *, strict: bool = False) -> AuthPrincipal | None:
        normalized = _clean_text(token)
        if not normalized:
            return None
        admin_key = _clean_text(self._admin_key_provider())
        if admin_key and normalized == admin_key:
            return self._admin_principal()
        token_hash = self._hash_token(normalized)
        with self._lock:
            for index, item in enumerate(self._items):
                if item.get("key_hash") != token_hash:
                    continue
                if not self._validate_item(item, strict=strict):
                    return None
                next_item = dict(item)
                next_item["last_used_at"] = _utc_now()
                next_item["updated_at"] = next_item["last_used_at"]
                next_item["request_count"] = max(0, int(next_item.get("request_count") or 0)) + 1
                self._items[index] = next_item
                self._save_items()
                return self._principal_from_item(next_item)
        return None

    def reserve_image_quota(self, principal: AuthPrincipal, amount: int) -> AuthPrincipal:
        if principal.is_admin:
            return principal
        normalized_amount = max(0, int(amount or 0))
        if normalized_amount == 0:
            return principal
        with self._lock:
            for index, item in enumerate(self._items):
                if str(item.get("id") or "") != principal.key_id:
                    continue
                if not self._validate_item(item, strict=True):
                    raise APIKeyAuthError("authorization is invalid")
                next_item = dict(item)
                current_image_count = max(0, int(next_item.get("image_count") or 0))
                max_image_count = _clean_optional_limit(next_item.get("max_image_count"))
                if max_image_count is not None and current_image_count + normalized_amount > max_image_count:
                    raise APIKeyAuthError("api key image quota exceeded", status_code=429)
                next_item["image_count"] = current_image_count + normalized_amount
                next_item["updated_at"] = _utc_now()
                self._items[index] = next_item
                self._save_items()
                return self._principal_from_item(next_item)
        raise APIKeyAuthError("authorization is invalid")


api_key_service = APIKeyService(config.api_keys_file)
