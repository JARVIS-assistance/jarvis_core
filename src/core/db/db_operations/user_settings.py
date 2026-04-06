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
