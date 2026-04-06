from __future__ import annotations

from uuid import uuid4

from ..db_connection import DBClient
from .common import now_iso


RECENT_WINDOW = 12
SUMMARY_TARGET_CHARS = 1800


def _fetch_messages_for_summary(
    db: DBClient, chat_id: str
) -> list[dict[str, str]]:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE chat_id = %s
            ORDER BY created_at ASC
            """,
            (chat_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
            """,
            (chat_id,),
        )
    return [
        {"id": str(row[0]), "role": str(row[1]), "content": str(row[2])}
        for row in cursor.fetchall()
    ]


def _shorten(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _build_summary_text(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        speaker = "User" if message["role"] == "user" else "Assistant"
        lines.append(f"- {speaker}: {_shorten(message['content'])}")
    summary = "Conversation summary:\n" + "\n".join(lines)
    if len(summary) <= SUMMARY_TARGET_CHARS:
        return summary
    return summary[: SUMMARY_TARGET_CHARS - 3].rstrip() + "..."


def rebuild_chat_summary(
    db: DBClient, *, chat_id: str, recent_window: int = RECENT_WINDOW
) -> None:
    messages = _fetch_messages_for_summary(db, chat_id=chat_id)
    if len(messages) <= recent_window:
        if db.backend == "postgres":
            db.conn.execute("DELETE FROM chat_summaries WHERE chat_id = %s", (chat_id,))
        else:
            db.conn.execute("DELETE FROM chat_summaries WHERE chat_id = ?", (chat_id,))
        db.conn.commit()
        return

    summary_messages = messages[:-recent_window]
    summary_text = _build_summary_text(summary_messages)
    summary_id = str(uuid4())
    now = now_iso()
    from_message_id = summary_messages[0]["id"]
    to_message_id = summary_messages[-1]["id"]

    try:
        if db.backend == "postgres":
            db.conn.execute("DELETE FROM chat_summaries WHERE chat_id = %s", (chat_id,))
            db.conn.execute(
                """
                INSERT INTO chat_summaries (
                    id, chat_id, summary_text, from_message_id, to_message_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (summary_id, chat_id, summary_text, from_message_id, to_message_id, now),
            )
        else:
            db.conn.execute("DELETE FROM chat_summaries WHERE chat_id = ?", (chat_id,))
            db.conn.execute(
                """
                INSERT INTO chat_summaries (
                    id, chat_id, summary_text, from_message_id, to_message_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (summary_id, chat_id, summary_text, from_message_id, to_message_id, now),
            )
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise


def get_latest_chat_summary(db: DBClient, *, chat_id: str) -> dict[str, str] | None:
    if db.backend == "postgres":
        cursor = db.conn.execute(
            """
            SELECT id, summary_text, from_message_id, to_message_id, created_at
            FROM chat_summaries
            WHERE chat_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chat_id,),
        )
    else:
        cursor = db.conn.execute(
            """
            SELECT id, summary_text, from_message_id, to_message_id, created_at
            FROM chat_summaries
            WHERE chat_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chat_id,),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "summary_text": str(row[1]),
        "from_message_id": str(row[2]) if row[2] is not None else "",
        "to_message_id": str(row[3]) if row[3] is not None else "",
        "created_at": str(row[4]),
    }
