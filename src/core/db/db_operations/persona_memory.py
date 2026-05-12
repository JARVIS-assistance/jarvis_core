from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..db_connection import DBClient
from .common import now_iso


DEFAULT_PERSONA_NAME = "Default Persona"
DEFAULT_PERSONA_DESCRIPTION = "Auto-created default persona per user."
DEFAULT_PERSONA_PROMPT = (
    "Use the base JARVIS style. Be natural, warm, concise, and conversational."
)
DEFAULT_PERSONA_TONE = "balanced"
DEFAULT_PERSONA_ALIAS = "default"


def ensure_default_persona_for_user(db: DBClient, user_id: str) -> dict[str, Any]:
    existing = get_selected_persona_for_user(db, user_id=user_id)
    if existing is not None:
        return existing

    persona_id = str(uuid4())
    user_persona_id = str(uuid4())
    now = now_iso()

    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, true)
                """,
                (
                    persona_id,
                    user_id,
                    DEFAULT_PERSONA_NAME,
                    DEFAULT_PERSONA_DESCRIPTION,
                    DEFAULT_PERSONA_PROMPT,
                    DEFAULT_PERSONA_TONE,
                ),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (%s, %s, %s, %s)
                """,
                (user_persona_id, user_id, persona_id, DEFAULT_PERSONA_ALIAS),
            )
            db.conn.execute(
                """
                UPDATE chats
                SET last_selected_user_persona_id = %s, last_message_at = %s
                WHERE id = (
                    SELECT id
                    FROM chats
                    WHERE user_id = %s AND status = 'ACTIVE'
                    ORDER BY last_message_at DESC
                    LIMIT 1
                )
                """,
                (user_persona_id, now, user_id),
            )
        else:
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persona_id,
                    user_id,
                    DEFAULT_PERSONA_NAME,
                    DEFAULT_PERSONA_DESCRIPTION,
                    DEFAULT_PERSONA_PROMPT,
                    DEFAULT_PERSONA_TONE,
                    1,
                ),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (?, ?, ?, ?)
                """,
                (user_persona_id, user_id, persona_id, DEFAULT_PERSONA_ALIAS),
            )
            db.conn.execute(
                """
                UPDATE chats
                SET last_selected_user_persona_id = ?, last_message_at = ?
                WHERE id = (
                    SELECT id
                    FROM chats
                    WHERE user_id = ? AND status = 'ACTIVE'
                    ORDER BY last_message_at DESC
                    LIMIT 1
                )
                """,
                (user_persona_id, now, user_id),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return {
        "user_persona_id": user_persona_id,
        "persona_id": persona_id,
        "name": DEFAULT_PERSONA_NAME,
        "description": DEFAULT_PERSONA_DESCRIPTION,
        "prompt_template": DEFAULT_PERSONA_PROMPT,
        "tone": DEFAULT_PERSONA_TONE,
        "alias": DEFAULT_PERSONA_ALIAS,
        "is_active": True,
    }


def _map_persona_row(row: Any) -> dict[str, Any]:
    return {
        "user_persona_id": str(row[0]),
        "persona_id": str(row[1]),
        "name": row[2],
        "description": row[3],
        "prompt_template": row[4],
        "tone": row[5],
        "alias": row[6],
        "is_active": bool(row[7]),
        "is_selected": bool(row[8]),
    }


def list_user_personas(db: DBClient, user_id: str) -> list[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                EXISTS (
                    SELECT 1
                    FROM chats c
                    WHERE c.user_id = up.user_id
                      AND c.status = 'ACTIVE'
                      AND c.last_selected_user_persona_id = up.id
                ) AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = %s
            ORDER BY is_selected DESC, p.name ASC
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                EXISTS (
                    SELECT 1
                    FROM chats c
                    WHERE c.user_id = up.user_id
                      AND c.status = 'ACTIVE'
                      AND c.last_selected_user_persona_id = up.id
                ) AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = ?
            ORDER BY is_selected DESC, p.name ASC
            """,
            (user_id,),
        )
    return [_map_persona_row(row) for row in cursor.fetchall()]


def get_selected_persona_for_user(db: DBClient, user_id: str) -> dict[str, Any] | None:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                true AS is_selected
            FROM chats c
            JOIN user_personas up ON up.id = c.last_selected_user_persona_id
            JOIN personas p ON p.id = up.persona_id
            WHERE c.user_id = %s
              AND c.status = 'ACTIVE'
              AND p.is_active = true
            ORDER BY c.last_message_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                1 AS is_selected
            FROM chats c
            JOIN user_personas up ON up.id = c.last_selected_user_persona_id
            JOIN personas p ON p.id = up.persona_id
            WHERE c.user_id = ?
              AND c.status = 'ACTIVE'
              AND p.is_active = 1
            ORDER BY c.last_message_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
    row = cursor.fetchone()
    if row is not None:
        return _map_persona_row(row)
    return _get_first_active_persona_for_user(db, user_id=user_id)


def _get_first_active_persona_for_user(
    db: DBClient, *, user_id: str
) -> dict[str, Any] | None:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                false AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = %s
              AND p.is_active = true
            ORDER BY
                CASE WHEN up.alias = %s THEN 1 ELSE 0 END,
                p.name ASC
            LIMIT 1
            """,
            (user_id, DEFAULT_PERSONA_ALIAS),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                0 AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = ?
              AND p.is_active = 1
            ORDER BY
                CASE WHEN up.alias = ? THEN 1 ELSE 0 END,
                p.name ASC
            LIMIT 1
            """,
            (user_id, DEFAULT_PERSONA_ALIAS),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return _map_persona_row(row)


def create_user_persona(
    db: DBClient,
    *,
    user_id: str,
    name: str,
    description: str | None,
    prompt_template: str,
    tone: str | None,
    alias: str | None,
) -> dict[str, Any]:
    persona_id = str(uuid4())
    user_persona_id = str(uuid4())

    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, true)
                """,
                (persona_id, user_id, name, description, prompt_template, tone),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (%s, %s, %s, %s)
                """,
                (user_persona_id, user_id, persona_id, alias),
            )
        else:
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (persona_id, user_id, name, description, prompt_template, tone, 1),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (?, ?, ?, ?)
                """,
                (user_persona_id, user_id, persona_id, alias),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return {
        "user_persona_id": user_persona_id,
        "persona_id": persona_id,
        "name": name,
        "description": description,
        "prompt_template": prompt_template,
        "tone": tone,
        "alias": alias,
        "is_active": True,
        "is_selected": False,
    }


def update_user_persona(
    db: DBClient,
    *,
    user_id: str,
    user_persona_id: str,
    name: str,
    description: str | None,
    prompt_template: str,
    tone: str | None,
    alias: str | None,
) -> dict[str, Any] | None:
    existing = get_user_persona_by_id(db, user_id=user_id, user_persona_id=user_persona_id)
    if existing is None:
        return None

    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                UPDATE personas
                SET name = %s, description = %s, prompt_template = %s, tone = %s
                WHERE id = %s AND owner_user_id = %s
                """,
                (
                    name,
                    description,
                    prompt_template,
                    tone,
                    existing["persona_id"],
                    user_id,
                ),
            )
            db.conn.execute(
                """
                UPDATE user_personas
                SET alias = %s
                WHERE id = %s AND user_id = %s
                """,
                (alias, user_persona_id, user_id),
            )
        else:
            db.conn.execute(
                """
                UPDATE personas
                SET name = ?, description = ?, prompt_template = ?, tone = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (
                    name,
                    description,
                    prompt_template,
                    tone,
                    existing["persona_id"],
                    user_id,
                ),
            )
            db.conn.execute(
                """
                UPDATE user_personas
                SET alias = ?
                WHERE id = ? AND user_id = ?
                """,
                (alias, user_persona_id, user_id),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    updated = get_user_persona_by_id(db, user_id=user_id, user_persona_id=user_persona_id)
    return updated


def get_user_persona_by_id(
    db: DBClient, *, user_id: str, user_persona_id: str
) -> dict[str, Any] | None:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                EXISTS (
                    SELECT 1
                    FROM chats c
                    WHERE c.user_id = up.user_id
                      AND c.status = 'ACTIVE'
                      AND c.last_selected_user_persona_id = up.id
                ) AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = %s AND up.id = %s
            """,
            (user_id, user_persona_id),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT
                up.id,
                p.id,
                p.name,
                p.description,
                p.prompt_template,
                p.tone,
                up.alias,
                p.is_active,
                EXISTS (
                    SELECT 1
                    FROM chats c
                    WHERE c.user_id = up.user_id
                      AND c.status = 'ACTIVE'
                      AND c.last_selected_user_persona_id = up.id
                ) AS is_selected
            FROM user_personas up
            JOIN personas p ON p.id = up.persona_id
            WHERE up.user_id = ? AND up.id = ?
            """,
            (user_id, user_persona_id),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return _map_persona_row(row)


def select_user_persona(
    db: DBClient, *, user_id: str, user_persona_id: str
) -> dict[str, Any] | None:
    existing = get_user_persona_by_id(db, user_id=user_id, user_persona_id=user_persona_id)
    if existing is None:
        return None

    now = now_iso()
    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                UPDATE chats
                SET last_selected_user_persona_id = %s, last_message_at = %s
                WHERE id = (
                    SELECT id
                    FROM chats
                    WHERE user_id = %s AND status = 'ACTIVE'
                    ORDER BY last_message_at DESC
                    LIMIT 1
                )
                """,
                (user_persona_id, now, user_id),
            )
        else:
            db.conn.execute(
                """
                UPDATE chats
                SET last_selected_user_persona_id = ?, last_message_at = ?
                WHERE id = (
                    SELECT id
                    FROM chats
                    WHERE user_id = ? AND status = 'ACTIVE'
                    ORDER BY last_message_at DESC
                    LIMIT 1
                )
                """,
                (user_persona_id, now, user_id),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise
    return get_user_persona_by_id(db, user_id=user_id, user_persona_id=user_persona_id)


def list_memory_items(
    db: DBClient,
    *,
    user_id: str,
    chat_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if db.backend == "postgres":
        if chat_id:
            cursor = db.conn.execute(
                """
                SELECT id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                FROM memory_items
                WHERE user_id = %s AND (chat_id = %s OR chat_id IS NULL)
                ORDER BY importance DESC, created_at DESC
                LIMIT %s
                """,
                (user_id, chat_id, limit),
            )
        else:
            cursor = db.conn.execute(
                """
                SELECT id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                FROM memory_items
                WHERE user_id = %s
                ORDER BY importance DESC, created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
    else:
        if chat_id:
            cursor = db.conn.execute(
                """
                SELECT id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                FROM memory_items
                WHERE user_id = ? AND (chat_id = ? OR chat_id IS NULL)
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, chat_id, limit),
            )
        else:
            cursor = db.conn.execute(
                """
                SELECT id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                FROM memory_items
                WHERE user_id = ?
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )

    items: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        items.append(
            {
                "id": str(row[0]),
                "user_id": str(row[1]),
                "chat_id": str(row[2]) if row[2] is not None else None,
                "type": row[3],
                "content": row[4],
                "importance": int(row[5]),
                "source_message_id": str(row[6]) if row[6] is not None else None,
                "created_at": str(row[7]),
                "expires_at": str(row[8]) if row[8] is not None else None,
            }
        )
    return items


def create_memory_item(
    db: DBClient,
    *,
    user_id: str,
    chat_id: str | None,
    memory_type: str,
    content: str,
    importance: int,
    source_message_id: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    memory_id = str(uuid4())
    now = now_iso()
    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                INSERT INTO memory_items (
                    id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    memory_id,
                    user_id,
                    chat_id,
                    memory_type,
                    content,
                    importance,
                    source_message_id,
                    now,
                    expires_at,
                ),
            )
        else:
            db.conn.execute(
                """
                INSERT INTO memory_items (
                    id, user_id, chat_id, type, content, importance, source_message_id, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    user_id,
                    chat_id,
                    memory_type,
                    content,
                    importance,
                    source_message_id,
                    now,
                    expires_at,
                ),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return {
        "id": memory_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "type": memory_type,
        "content": content,
        "importance": importance,
        "source_message_id": source_message_id,
        "created_at": now,
        "expires_at": expires_at,
    }
