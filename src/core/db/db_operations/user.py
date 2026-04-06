from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from ..db_connection import DBClient
from .common import now_iso
from .user_settings import ensure_user_settings


def create_user(
    db: DBClient, email: str, name: Optional[str] = None
) -> dict[str, Any]:
    """users 테이블에 사용자 생성 + 기본 persona/chat 초기화.

    패스워드는 gateway가 관리하므로 여기서는 저장하지 않음.
    """
    user_id = str(uuid4())
    persona_id = str(uuid4())
    user_persona_id = str(uuid4())
    chat_id = str(uuid4())
    now = now_iso()
    persona_name = "Default Persona"
    persona_description = "Auto-created default persona per user."
    persona_prompt = "You are Jarvis, a practical and concise assistant for this user."
    persona_tone = "balanced"
    persona_alias = "default"

    try:
        if db.backend == "postgres":
            db.conn.execute(
                """
                INSERT INTO users (id, email, name, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'ACTIVE', %s, %s)
                """,
                (user_id, email, name, now, now),
            )
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, true)
                """,
                (persona_id, user_id, persona_name, persona_description, persona_prompt, persona_tone),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (%s, %s, %s, %s)
                """,
                (user_persona_id, user_id, persona_id, persona_alias),
            )
            db.conn.execute(
                """
                INSERT INTO chats (id, user_id, status, last_selected_user_persona_id, created_at, last_message_at)
                VALUES (%s, %s, 'ACTIVE', %s, %s, %s)
                """,
                (chat_id, user_id, user_persona_id, now, now),
            )
        else:
            db.conn.execute(
                """
                INSERT INTO users (id, email, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, name, "ACTIVE", now, now),
            )
            db.conn.execute(
                """
                INSERT INTO personas (id, owner_user_id, name, description, prompt_template, tone, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (persona_id, user_id, persona_name, persona_description, persona_prompt, persona_tone, 1),
            )
            db.conn.execute(
                """
                INSERT INTO user_personas (id, user_id, persona_id, alias)
                VALUES (?, ?, ?, ?)
                """,
                (user_persona_id, user_id, persona_id, persona_alias),
            )
            db.conn.execute(
                """
                INSERT INTO chats (id, user_id, status, last_selected_user_persona_id, created_at, last_message_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, "ACTIVE", user_persona_id, now, now),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise
    ensure_user_settings(db, user_id=user_id)
    return {"id": user_id, "email": email, "name": name}


def find_user_by_email(db: DBClient, email: str) -> Optional[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            "SELECT id, email, name, status FROM users WHERE email = %s",
            (email,),
        )
    else:
        cursor = db.conn.execute(
            "SELECT id, email, name, status FROM users WHERE email = ?",
            (email,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "email": row[1],
        "name": row[2],
        "status": row[3],
    }


def find_user_by_id(db: DBClient, user_id: str) -> Optional[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            "SELECT id, email, name, status FROM users WHERE id = %s",
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            "SELECT id, email, name, status FROM users WHERE id = ?",
            (user_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "email": row[1],
        "name": row[2],
        "status": row[3],
    }
