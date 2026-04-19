import json
import logging
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".butler" / "state.db"

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    user_id TEXT,
    model TEXT,
    model_config TEXT,
    system_prompt TEXT,
    parent_session_id TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    title TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);
"""


class ButlerIntegrationSessionStore:
    _WRITE_MAX_RETRIES = 10
    _WRITE_RETRY_MIN_S = 0.020
    _WRITE_RETRY_MAX_S = 0.100

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._write_count = 0
        self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=1.0,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.executescript(FTS_SQL)
        conn.commit()

    def _execute_with_retry(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_conn()
        retries = 0
        while retries < self._WRITE_MAX_RETRIES:
            try:
                return conn.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and retries < self._WRITE_MAX_RETRIES - 1:
                    wait = random.uniform(self._WRITE_RETRY_MIN_S, self._WRITE_RETRY_MAX_S)
                    time.sleep(wait)
                    retries += 1
                    continue
                raise
        raise RuntimeError("database write retry loop exited unexpectedly")

    def create_session(
        self,
        source: str = "butler",
        user_id: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        parent_session_id: str | None = None,
    ) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        started_at = time.time()

        self._execute_with_retry(
            """INSERT INTO sessions 
               (id, source, user_id, model, system_prompt, parent_session_id, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, source, user_id, model, system_prompt, parent_session_id, started_at),
        )
        self._get_conn().commit()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list | None = None,
        tool_name: str | None = None,
    ) -> int:
        timestamp = time.time()
        tc_json = json.dumps(tool_calls) if tool_calls else None

        cursor = self._execute_with_retry(
            """INSERT INTO messages 
               (session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, tool_call_id, tc_json, tool_name, timestamp),
        )
        self._get_conn().commit()

        self._execute_with_retry(
            "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
            (session_id,),
        )
        self._get_conn().commit()
        if cursor.lastrowid is None:
            raise RuntimeError("message insert did not return a row id")
        return cursor.lastrowid

    def get_messages(self, session_id: str) -> List[dict]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def list_sessions(
        self,
        source: str | None = None,
        user_id: str | None = None,
        limit: int = 10,
    ) -> List[dict]:
        conn = self._get_conn()
        sql = "SELECT * FROM sessions"
        params = []
        where = []
        if source:
            where.append("source = ?")
            params.append(source)
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))

    def end_session(self, session_id: str, end_reason: str | None = None) -> None:
        ended_at = time.time()
        self._execute_with_retry(
            "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ?",
            (ended_at, end_reason, session_id),
        )
        self._get_conn().commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


HermesSessionDB = ButlerIntegrationSessionStore
