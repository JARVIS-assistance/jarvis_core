from __future__ import annotations

from uuid import uuid4

from ..db_connection import DBClient
from .chat_summary import RECENT_WINDOW, rebuild_chat_summary
from .common import now_iso


def add_message(db: DBClient, session_id: str, role: str, content: str) -> None:
    message_id = str(uuid4())
    now = now_iso()
    if db.backend == "postgres":
        db.conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (message_id, session_id, role, content, now),
        )
        db.conn.execute("UPDATE chats SET last_message_at = %s WHERE id = %s", (now, session_id))
    else:
        db.conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, now),
        )
        db.conn.execute("UPDATE chats SET last_message_at = ? WHERE id = ?", (now, session_id))
    db.conn.commit()
    rebuild_chat_summary(db, chat_id=session_id, recent_window=RECENT_WINDOW)


def list_recent_messages(
    db: DBClient, session_id: str, *, limit: int = 12
) -> list[dict[str, str]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE chat_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        )

    rows = cursor.fetchall()
    rows.reverse()
    return [{"role": str(row[0]), "content": str(row[1])} for row in rows]
