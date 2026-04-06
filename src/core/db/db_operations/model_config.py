from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import uuid4

from ..db_connection import DBClient
from .common import now_iso

ProviderMode = Literal["token", "local"]


def _row_to_model_config(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "provider_mode": row[1],
        "provider_name": row[2],
        "model_name": row[3],
        "api_key": row[4],
        "endpoint": row[5],
        "is_active": bool(row[6]),
        "is_default": bool(row[7]),
        "supports_stream": bool(row[8]),
        "supports_realtime": bool(row[9]),
        "transport": row[10],
        "input_modalities": row[11],
        "output_modalities": row[12],
    }


def list_user_model_configs(db: DBClient, user_id: str) -> list[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE user_id = %s
            ORDER BY is_default DESC, updated_at DESC
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE user_id = ?
            ORDER BY is_default DESC, updated_at DESC
            """,
            (user_id,),
        )
    return [_row_to_model_config(row) for row in cursor.fetchall()]


def get_active_model_for_user(db: DBClient, user_id: str) -> Optional[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE user_id = %s AND is_active = true
            ORDER BY is_default DESC, updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE user_id = ? AND is_active = 1
            ORDER BY is_default DESC, updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_model_config(row)


def get_model_config_by_id_for_user(
    db: DBClient, user_id: str, model_config_id: str
) -> Optional[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE id = %s AND user_id = %s
            LIMIT 1
            """,
            (model_config_id, user_id),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE id = ? AND user_id = ?
            LIMIT 1
            """,
            (model_config_id, user_id),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_model_config(row)


def create_user_model_config(
    db: DBClient,
    user_id: str,
    provider_mode: ProviderMode,
    provider_name: str,
    model_name: str,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    is_default: bool = False,
    supports_stream: bool = True,
    supports_realtime: bool = False,
    transport: str = "http_sse",
    input_modalities: str = "text",
    output_modalities: str = "text",
) -> dict[str, Any]:
    now = now_iso()
    row_id = str(uuid4())

    if is_default:
        if db.backend == "postgres":
            db.conn.execute(
                "UPDATE ai_model_configs SET is_default = false, updated_at = %s WHERE user_id = %s",
                (now, user_id),
            )
        else:
            db.conn.execute(
                "UPDATE ai_model_configs SET is_default = 0, updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )

    if db.backend == "postgres":
        db.conn.execute(
            """
            INSERT INTO ai_model_configs (
                id, user_id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                supports_stream, supports_realtime, transport, input_modalities, output_modalities, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row_id,
                user_id,
                provider_mode,
                provider_name,
                model_name,
                api_key,
                endpoint,
                is_default,
                supports_stream,
                supports_realtime,
                transport,
                input_modalities,
                output_modalities,
                now,
                now,
            ),
        )
    else:
        db.conn.execute(
            """
            INSERT INTO ai_model_configs (
                id, user_id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                supports_stream, supports_realtime, transport, input_modalities, output_modalities, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                user_id,
                provider_mode,
                provider_name,
                model_name,
                api_key,
                endpoint,
                1,
                int(is_default),
                int(supports_stream),
                int(supports_realtime),
                transport,
                input_modalities,
                output_modalities,
                now,
                now,
            ),
        )

    db.conn.commit()
    return {
        "id": row_id,
        "provider_mode": provider_mode,
        "provider_name": provider_name,
        "model_name": model_name,
        "api_key": api_key,
        "endpoint": endpoint,
        "is_active": True,
        "is_default": is_default,
        "supports_stream": supports_stream,
        "supports_realtime": supports_realtime,
        "transport": transport,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
    }


def update_user_model_config(
    db: DBClient,
    user_id: str,
    model_config_id: str,
    provider_mode: ProviderMode,
    provider_name: str,
    model_name: str,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    is_default: bool = False,
    supports_stream: bool = True,
    supports_realtime: bool = False,
    transport: str = "http_sse",
    input_modalities: str = "text",
    output_modalities: str = "text",
) -> Optional[dict[str, Any]]:
    existing = get_model_config_by_id_for_user(db, user_id, model_config_id)
    if existing is None:
        return None

    now = now_iso()

    if is_default:
        if db.backend == "postgres":
            db.conn.execute(
                """
                UPDATE ai_model_configs
                SET is_default = false, updated_at = %s
                WHERE user_id = %s AND id <> %s
                """,
                (now, user_id, model_config_id),
            )
        else:
            db.conn.execute(
                """
                UPDATE ai_model_configs
                SET is_default = 0, updated_at = ?
                WHERE user_id = ? AND id <> ?
                """,
                (now, user_id, model_config_id),
            )

    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            UPDATE ai_model_configs
            SET provider_mode = %s,
                provider_name = %s,
                model_name = %s,
                api_key = %s,
                endpoint = %s,
                is_default = %s,
                supports_stream = %s,
                supports_realtime = %s,
                transport = %s,
                input_modalities = %s,
                output_modalities = %s,
                updated_at = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                      supports_stream, supports_realtime, transport, input_modalities, output_modalities
            """,
            (
                provider_mode,
                provider_name,
                model_name,
                api_key,
                endpoint,
                is_default,
                supports_stream,
                supports_realtime,
                transport,
                input_modalities,
                output_modalities,
                now,
                model_config_id,
                user_id,
            ),
        )
        row = cursor.fetchone()
    else:
        db.conn.execute(
            """
            UPDATE ai_model_configs
            SET provider_mode = ?,
                provider_name = ?,
                model_name = ?,
                api_key = ?,
                endpoint = ?,
                is_default = ?,
                supports_stream = ?,
                supports_realtime = ?,
                transport = ?,
                input_modalities = ?,
                output_modalities = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                provider_mode,
                provider_name,
                model_name,
                api_key,
                endpoint,
                int(is_default),
                int(supports_stream),
                int(supports_realtime),
                transport,
                input_modalities,
                output_modalities,
                now,
                model_config_id,
                user_id,
            ),
        )
        cursor = db.conn.execute(
            """
            SELECT id, provider_mode, provider_name, model_name, api_key, endpoint, is_active, is_default,
                   supports_stream, supports_realtime, transport, input_modalities, output_modalities
            FROM ai_model_configs
            WHERE id = ? AND user_id = ?
            LIMIT 1
            """,
            (model_config_id, user_id),
        )
        row = cursor.fetchone()

    db.conn.commit()
    if row is None:
        return None
    return _row_to_model_config(row)
