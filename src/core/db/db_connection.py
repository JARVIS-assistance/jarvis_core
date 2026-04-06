from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import quote_plus, urlsplit, urlunsplit

try:
    import psycopg
except ImportError:  # pragma: no cover - optional dependency for PostgreSQL runtime
    psycopg = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency for local env loading
    load_dotenv = None

# Load local env files explicitly so running from the repo root still picks up
# jarvis_core/.env, which is also used by gateway through this module.
if load_dotenv is not None:
    repo_root = Path(__file__).resolve().parents[4]
    for env_path in (repo_root / "jarvis_core" / ".env", repo_root / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


@dataclass
class DBClient:
    backend: Literal["sqlite", "postgres"]
    conn: Any


def _describe_postgres_target(db_url: str) -> str:
    parts = urlsplit(db_url)
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    user = parts.username or "<unknown>"
    db_name = parts.path.lstrip("/") or "postgres"
    return f"{user}@{host}:{port}/{db_name}"


def get_db_path() -> str:
    default_path = Path("data") / "jarvis_core.db"
    db_path = os.getenv("JARVIS_CORE_DB", str(default_path))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_database_url() -> Optional[str]:
    explicit_url = os.getenv("JARVIS_CORE_DB_URL")
    user = os.getenv("JARVIS_CORE_DB_USER")
    password = os.getenv("JARVIS_CORE_DB_PASSWORD")

    if explicit_url:
        if user and password and explicit_url.startswith("postgresql"):
            parts = urlsplit(explicit_url)
            host = parts.hostname or "localhost"
            port = parts.port
            hostport = f"{host}:{port}" if port else host
            netloc = f"{quote_plus(user)}:{quote_plus(password)}@{hostport}"
            return urlunsplit(
                (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
            )
        return explicit_url

    host = os.getenv("JARVIS_CORE_DB_HOST")
    port = os.getenv("JARVIS_CORE_DB_PORT", "5432")
    db_name = os.getenv("JARVIS_CORE_DB_NAME", "postgres")
    if host and user and password:
        return (
            f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
            f"{host}:{port}/{db_name}"
        )
    return None


def connect(db_path: Optional[str] = None) -> DBClient:
    db_url = get_database_url()
    if db_path is None and db_url and db_url.startswith("postgresql"):
        if psycopg is None:
            raise RuntimeError(
                "JARVIS_CORE_DB_URL is PostgreSQL but psycopg is not installed. "
                "Install `psycopg[binary]`."
            )
        print(
            f"Connected to PostgreSQL database: {_describe_postgres_target(db_url)}",
            flush=True,
        )
        return DBClient(backend="postgres", conn=psycopg.connect(db_url))

    resolved_db_path = db_path or get_db_path()
    sqlite_conn = sqlite3.connect(resolved_db_path, check_same_thread=False)
    print(f"Connected to SQLite database at {resolved_db_path}", flush=True)
    return DBClient(backend="sqlite", conn=sqlite_conn)
