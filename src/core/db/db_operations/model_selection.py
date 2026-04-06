from __future__ import annotations

from typing import Optional

from ..db_connection import DBClient
from .common import now_iso


def get_user_ai_selection(db: DBClient, user_id: str) -> Optional[dict[str, Optional[str]]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT realtime_model_config_id, deep_model_config_id
            FROM user_ai_model_selection
            WHERE user_id = %s
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT realtime_model_config_id, deep_model_config_id
            FROM user_ai_model_selection
            WHERE user_id = ?
            """,
            (user_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "realtime_model_config_id": str(row[0]) if row[0] is not None else None,
        "deep_model_config_id": str(row[1]) if row[1] is not None else None,
    }


def set_user_ai_selection(
    db: DBClient,
    user_id: str,
    realtime_model_config_id: Optional[str],
    deep_model_config_id: Optional[str],
) -> dict[str, Optional[str]]:
    now = now_iso()
    if db.backend == "postgres":
        db.conn.execute(
            """
            INSERT INTO user_ai_model_selection (
                user_id, realtime_model_config_id, deep_model_config_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
              realtime_model_config_id = EXCLUDED.realtime_model_config_id,
              deep_model_config_id = EXCLUDED.deep_model_config_id,
              updated_at = EXCLUDED.updated_at
            """,
            (user_id, realtime_model_config_id, deep_model_config_id, now, now),
        )
    else:
        db.conn.execute(
            """
            INSERT INTO user_ai_model_selection (
                user_id, realtime_model_config_id, deep_model_config_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                realtime_model_config_id = excluded.realtime_model_config_id,
                deep_model_config_id = excluded.deep_model_config_id,
                updated_at = excluded.updated_at
            """,
            (user_id, realtime_model_config_id, deep_model_config_id, now, now),
        )
    db.conn.commit()
    return {
        "realtime_model_config_id": realtime_model_config_id,
        "deep_model_config_id": deep_model_config_id,
    }
