from __future__ import annotations

import json
from typing import Any

from ..db_connection import DBClient
from .common import now_iso


def ensure_user_settings(db: DBClient, user_id: str) -> dict[str, Any]:
    existing = get_user_settings(db, user_id=user_id)
    if existing is not None:
        return existing

    now = now_iso()
    metadata = json.dumps({}, ensure_ascii=False)
    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                INSERT INTO user_settings (
                    user_id, locale, timezone, response_style, metadata, created_at, updated_at
                )
                VALUES (%s, 'ko-KR', 'Asia/Seoul', 'balanced', %s::jsonb, %s, %s)
                """,
                (user_id, metadata, now, now),
            )
        else:
            db.conn.execute(
                """
                INSERT INTO user_settings (
                    user_id, locale, timezone, response_style, metadata, created_at, updated_at
                )
                VALUES (?, 'ko-KR', 'Asia/Seoul', 'balanced', ?, ?, ?)
                """,
                (user_id, metadata, now, now),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return {
        "user_id": user_id,
        "locale": "ko-KR",
        "timezone": "Asia/Seoul",
        "response_style": "balanced",
        "metadata": {},
    }


def get_user_settings(db: DBClient, user_id: str) -> dict[str, Any] | None:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT user_id, locale, timezone, response_style, metadata
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT user_id, locale, timezone, response_style, metadata
            FROM user_settings
            WHERE user_id = ?
            """,
            (user_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None

    raw_metadata = row[4]
    metadata: dict[str, Any]
    if isinstance(raw_metadata, dict):
        metadata = raw_metadata
    elif raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except (TypeError, json.JSONDecodeError):
            metadata = {}
    else:
        metadata = {}

    return {
        "user_id": str(row[0]),
        "locale": row[1],
        "timezone": row[2],
        "response_style": row[3],
        "metadata": metadata,
    }


def get_runtime_profile(db: DBClient, user_id: str) -> dict[str, Any]:
    settings = ensure_user_settings(db, user_id=user_id)
    metadata = settings.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    profile = metadata.get("runtime_profile")
    return profile if isinstance(profile, dict) else {}


def set_runtime_profile(
    db: DBClient,
    *,
    user_id: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    settings = ensure_user_settings(db, user_id=user_id)
    raw_metadata = settings.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    now = now_iso()
    normalized = _normalize_runtime_profile(profile, updated_at=now)
    metadata["runtime_profile"] = normalized
    encoded_metadata = json.dumps(metadata, ensure_ascii=False)

    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                UPDATE user_settings
                SET metadata = %s::jsonb, updated_at = %s
                WHERE user_id = %s
                """,
                (encoded_metadata, now, user_id),
            )
        else:
            db.conn.execute(
                """
                UPDATE user_settings
                SET metadata = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (encoded_metadata, now, user_id),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return normalized


def _normalize_runtime_profile(
    profile: dict[str, Any],
    *,
    updated_at: str,
) -> dict[str, Any]:
    raw_applications = profile.get("applications")
    applications = raw_applications if isinstance(raw_applications, list) else []
    terminal = profile.get("terminal")
    metadata = profile.get("metadata")
    capabilities = profile.get("capabilities")
    return {
        "platform": _string_or_none(profile.get("platform")),
        "default_browser": _string_or_none(profile.get("default_browser")),
        "capabilities": _normalize_capabilities(capabilities),
        "applications": [
            app
            for raw_app in applications
            if isinstance(raw_app, dict)
            for app in [_normalize_application(raw_app)]
            if app is not None
        ],
        "terminal": (
            _normalize_terminal_profile(terminal)
            if isinstance(terminal, dict)
            else _normalize_terminal_profile({})
        ),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "updated_at": updated_at,
    }


def _normalize_application(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = _string_or_none(raw.get("name")) or _string_or_none(raw.get("display_name"))
    if not name:
        return None
    aliases = _string_list(raw.get("aliases"))
    return {
        "id": _string_or_none(raw.get("id")),
        "name": name,
        "display_name": _string_or_none(raw.get("display_name")),
        "aliases": aliases,
        "bundle_id": _string_or_none(raw.get("bundle_id")),
        "path": _string_or_none(raw.get("path")),
        "executable": _string_or_none(raw.get("executable")),
        "kind": _string_or_none(raw.get("kind")),
        "capabilities": _string_list(raw.get("capabilities")),
        "categories": _string_list(raw.get("categories")),
        "keywords": _string_list(raw.get("keywords")),
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
    }


def _normalize_terminal_profile(raw: dict[str, Any]) -> dict[str, Any]:
    env = raw.get("env")
    return {
        "enabled": bool(raw.get("enabled", False)),
        "shell": _string_or_none(raw.get("shell")),
        "shell_path": _string_or_none(raw.get("shell_path")),
        "cwd": _string_or_none(raw.get("cwd")),
        "env": (
            {str(key): str(value) for key, value in env.items()}
            if isinstance(env, dict)
            else {}
        ),
        "allowed_commands": _string_list(raw.get("allowed_commands")),
        "allowed_cwds": _string_list(raw.get("allowed_cwds")),
        "supports_pty": bool(raw.get("supports_pty", False)),
        "requires_confirm": bool(raw.get("requires_confirm", True)),
        "timeout_seconds": _positive_int(
            raw.get("timeout_seconds"),
            default=30,
            maximum=600,
        ),
    }


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        normalized = _string_or_none(item)
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalize_capabilities(value: Any) -> list[Any] | dict[str, Any]:
    if isinstance(value, dict):
        normalized_dict: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.strip():
                normalized_dict[key.strip()] = item
        return normalized_dict
    if not isinstance(value, list):
        return []
    items: list[Any] = []
    for item in value:
        if isinstance(item, str):
            normalized = _string_or_none(item)
            if normalized and normalized not in items:
                items.append(normalized)
        elif isinstance(item, dict):
            name = _string_or_none(
                item.get("name") or item.get("capability") or item.get("id")
            )
            if not name:
                continue
            normalized_item = dict(item)
            normalized_item["name"] = name
            items.append(normalized_item)
    return items


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)
