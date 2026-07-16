"""SQLite üzerinden CV kayıtları — düz sqlite3, ORM yok."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "cvradar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    name TEXT NOT NULL,
    category_key TEXT NOT NULL,
    category_score REAL NOT NULL,
    raw_text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    tags TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    thumbnail_path TEXT,
    pages_dir TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_cv(
    filename: str,
    original_path: str,
    name: str,
    category_key: str,
    category_score: float,
    raw_text: str,
    embedding: list,
    tags: list,
    page_count: int,
    thumbnail_path: str,
    pages_dir: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO cvs
            (filename, original_path, name, category_key, category_score, raw_text,
             embedding, tags, page_count, thumbnail_path, pages_dir)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                filename,
                original_path,
                name,
                category_key,
                category_score,
                raw_text,
                json.dumps(embedding),
                json.dumps(tags, ensure_ascii=False),
                page_count,
                thumbnail_path,
                pages_dir,
            ),
        )
        return cur.lastrowid


def get_cv(cv_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()


def list_cvs() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM cvs ORDER BY created_at DESC").fetchall()
