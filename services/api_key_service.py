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


@dataclass(frozen=True)
class AuthPrincipal:
    key_id: str
    name: str
    kind: str
    scopes: tuple[str, ...]
    allowed_models: tuple[str, ...]
    is_admin: bool = False

    def allows_model(self, model: str) -> bool:
        model_id = _clean_text(model) or "auto"
        return self.is_admin or not self.allowed_models or model_id in self.allowed_models


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
            "request_count": int(item.get("request_count") or 0),
        }

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
            name: str | None = None,
            enabled: bool | None = None,
            allowed_models: list[str] | None = None,
            scopes: list[str] | None = None,
            expires_at: str | None = None,
    ) -> dict[str, object] | None:
        normalized_key_id = _clean_text(key_id)
        with self._lock:
            for index, item in enumerate(self._items):
                if item.get("id") != normalized_key_id:
                    continue
                next_item = dict(item)
                if name is not None:
                    next_item["name"] = _clean_text(name) or next_item["name"]
                if enabled is not None:
                    next_item["enabled"] = bool(enabled)
                if allowed_models is not None:
                    next_item["allowed_models"] = _clean_list(allowed_models)
                if scopes is not None:
                    next_item["scopes"] = _clean_list(scopes) or ["inference"]
                if expires_at is not None:
                    next_item["expires_at"] = _clean_text(expires_at) or None
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
                next_item["request_count"] = 0
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

    def authenticate(self, token: str) -> AuthPrincipal | None:
        normalized = _clean_text(token)
        if not normalized:
            return None
        admin_key = _clean_text(self._admin_key_provider())
        if admin_key and normalized == admin_key:
            return AuthPrincipal(
                key_id="admin",
                name="admin",
                kind="admin",
                scopes=("admin", "inference"),
                allowed_models=(),
                is_admin=True,
            )
        token_hash = self._hash_token(normalized)
        with self._lock:
            for index, item in enumerate(self._items):
                if item.get("key_hash") != token_hash:
                    continue
                if not bool(item.get("enabled")) or _is_expired(item.get("expires_at")):
                    return None
                next_item = dict(item)
                next_item["last_used_at"] = _utc_now()
                next_item["updated_at"] = next_item["last_used_at"]
                next_item["request_count"] = int(next_item.get("request_count") or 0) + 1
                self._items[index] = next_item
                self._save_items()
                return AuthPrincipal(
                    key_id=str(next_item.get("id")),
                    name=str(next_item.get("name") or "client"),
                    kind="client",
                    scopes=tuple(_clean_list(next_item.get("scopes")) or ["inference"]),
                    allowed_models=tuple(_clean_list(next_item.get("allowed_models"))),
                    is_admin=False,
                )
        return None


api_key_service = APIKeyService(config.api_keys_file)
