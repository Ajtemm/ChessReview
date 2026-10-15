"""SQLite baza: čuvanje partija."""

import sqlite3
from pathlib import Path

from app.config import load_config, resolve_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    url             TEXT PRIMARY KEY,           -- jedinstveni ključ partije
    uuid            TEXT UNIQUE,
    pgn             TEXT NOT NULL,
    white           TEXT NOT NULL,
    black           TEXT NOT NULL,
    white_rating    INTEGER,
    black_rating    INTEGER,
    result          TEXT NOT NULL,              -- '1-0', '0-1', '1/2-1/2'
    my_color        TEXT NOT NULL,              -- 'white' ili 'black'
    end_time        TEXT NOT NULL,              -- ISO datum završetka (UTC)
    time_control    TEXT,                       -- npr. '180+2'
    time_class      TEXT,                       -- bullet / blitz / rapid / daily
    analysis_status TEXT NOT NULL DEFAULT 'pending',  -- pending / running / done / error
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_games_end_time ON games(end_time);
"""

GAME_FIELDS = (
    "url", "uuid", "pgn", "white", "black", "white_rating", "black_rating",
    "result", "my_color", "end_time", "time_control", "time_class",
)


def get_db_path() -> Path:
    return resolve_path(load_config()["database_path"])


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Otvara konekciju i pravi tabele ako ne postoje."""
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_game(conn: sqlite3.Connection, game: dict) -> bool:
    """Ubacuje partiju ako već ne postoji. Vraća True ako je partija nova."""
    columns = ", ".join(GAME_FIELDS)
    placeholders = ", ".join(f":{f}" for f in GAME_FIELDS)
    cur = conn.execute(
        f"INSERT OR IGNORE INTO games ({columns}) VALUES ({placeholders})",
        {f: game.get(f) for f in GAME_FIELDS},
    )
    return cur.rowcount == 1


def count_games(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]


def list_games(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """Partije od najnovije ka najstarijoj."""
    sql = "SELECT * FROM games ORDER BY end_time DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()
