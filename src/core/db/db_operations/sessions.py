from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from ..db_connection import DBClient
from .common import now_iso
from .user_settings import ensure_user_settings


def _create_user_sqlite(db: DBClient) -> str:
    user_id = str(uuid4())
    now = now_iso()
    email = f"guest+{user_id}@local.jarvis"
    db.conn.execute(
        "INSERT INTO users (id, email, name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, "Guest", "ACTIVE", now, now),
    )
    return user_id


def _create_user_postgres(db: DBClient) -> str:
    user_id = str(uuid4())
    email = f"guest+{user_id}@local.jarvis"
    db.conn.execute(
        """
        INSERT INTO users (id, email, name, status)
        VALUES (%s, %s, %s, 'ACTIVE')
        """,
        (user_id, email, "Guest"),
    )
    return user_id


def create_session(db: DBClient) -> dict[str, Any]:
    user_id = _create_user_postgres(db) if db.backend == "postgres" else _create_user_sqlite(db)
    session_id = str(uuid4())
    now = now_iso()
    if db.backend == "postgres":
        db.conn.execute(
            """
            INSERT INTO chats (id, user_id, status, created_at, last_message_at)
            VALUES (%s, %s, 'ACTIVE', %s, %s)
            """,
            (session_id, user_id, now, now),
        )
    else:
        db.conn.execute(
            """
            INSERT INTO chats (id, user_id, status, created_at, last_message_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, "ACTIVE", now, now),
        )
    db.conn.commit()
    return {"id": session_id, "created_at": now}


def get_session(db: DBClient, session_id: str) -> Optional[dict[str, Any]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            "SELECT id, status, created_at, last_message_at FROM chats WHERE id = %s",
            (session_id,),
        )
    else:
        cursor = db.conn.execute(
            "SELECT id, status, created_at, last_message_at FROM chats WHERE id = ?",
            (session_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": str(row[0]), "status": row[1], "created_at": str(row[2]), "updated_at": str(row[3])}


def ensure_user_exists(db: DBClient, user_id: str, email: str, name: str = "User") -> None:
    if db.backend == "postgres":
        cursor = db.conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
    else:
        cursor = db.conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    if cursor.fetchone() is not None:
        ensure_user_settings(db, user_id=user_id)
        return

    now = now_iso()
    if db.backend == "postgres":
        db.conn.execute(
            """
            INSERT INTO users (id, email, name, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'ACTIVE', %s, %s)
            """,
            (user_id, email, name, now, now),
        )
    else:
        db.conn.execute(
            """
            INSERT INTO users (id, email, name, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, email, name, "ACTIVE", now, now),
        )
    db.conn.commit()
    ensure_user_settings(db, user_id=user_id)


def get_or_create_session_for_user(db: DBClient, user_id: str, email: str) -> dict[str, Any]:
    ensure_user_exists(db, user_id=user_id, email=email)
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, status, created_at, last_message_at
            FROM chats
            WHERE user_id = %s AND status = 'ACTIVE'
            ORDER BY last_message_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, status, created_at, last_message_at
            FROM chats
            WHERE user_id = ? AND status = 'ACTIVE'
            ORDER BY last_message_at DESC
            LIMIT 1
            """,
            (user_id,),
        )

    row = cursor.fetchone()
    if row is not None:
        return {"id": str(row[0]), "status": row[1], "created_at": str(row[2]), "updated_at": str(row[3])}

    session_id = str(uuid4())
    now = now_iso()
    if db.backend == "postgres":
        db.conn.execute(
            """
            INSERT INTO chats (id, user_id, status, created_at, last_message_at)
            VALUES (%s, %s, 'ACTIVE', %s, %s)
            """,
            (session_id, user_id, now, now),
        )
    else:
        db.conn.execute(
            """
            INSERT INTO chats (id, user_id, status, created_at, last_message_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, "ACTIVE", now, now),
        )
    db.conn.commit()
    return {"id": session_id, "status": "ACTIVE", "created_at": now, "updated_at": now}
