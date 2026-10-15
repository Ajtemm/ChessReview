"""SQLite baza: čuvanje partija i analize poteza."""

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
    white_accuracy  REAL,                       -- tačnost partije (Lichess formula)
    black_accuracy  REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_games_end_time ON games(end_time);

-- Analiza po polupotezu; ocene su uvek iz ugla belog (kao eval bar)
CREATE TABLE IF NOT EXISTS moves (
    game_url         TEXT NOT NULL REFERENCES games(url) ON DELETE CASCADE,
    ply              INTEGER NOT NULL,          -- redni broj polupoteza od 1
    move_number      INTEGER NOT NULL,          -- broj poteza kao u notaciji
    color            TEXT NOT NULL,             -- 'white' ili 'black' (ko vuče potez)
    fen_before       TEXT NOT NULL,
    move_san         TEXT NOT NULL,
    move_uci         TEXT NOT NULL,
    eval_before_cp   INTEGER,                   -- centipešaci; NULL ako je mat
    eval_before_mate INTEGER,                   -- mat u N (+ beli matira, - crni)
    eval_after_cp    INTEGER,
    eval_after_mate  INTEGER,
    best_move_san    TEXT,
    best_move_uci    TEXT,
    pv               TEXT,                      -- glavna varijanta u SAN-u
    second_best_uci  TEXT,                      -- drugi najbolji potez (MultiPV 2)
    second_eval_cp   INTEGER,                   -- ocena posle drugog najboljeg poteza
    second_eval_mate INTEGER,
    classification   TEXT,                      -- best / excellent / ... / blunder / book
    PRIMARY KEY (game_url, ply)
);
"""

# Kolone dodate posle prve verzije šeme; dodajemo ih u postojeće baze
ADDED_COLUMNS = {
    "games": {"white_accuracy": "REAL", "black_accuracy": "REAL"},
    "moves": {
        "second_best_uci": "TEXT", "second_eval_cp": "INTEGER",
        "second_eval_mate": "INTEGER", "classification": "TEXT",
    },
}

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
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL: čitanje iz API-ja ne čeka na upis analize iz pozadine
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    return conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, col_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
    conn.commit()


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


def get_game(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM games WHERE url = ?", (url,)).fetchone()


def game_id(url: str) -> str:
    """Kratak ID partije: broj na kraju chess.com URL-a."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def get_game_by_id(conn: sqlite3.Connection, gid: str) -> sqlite3.Row | None:
    """Partija po kratkom ID-u (broj na kraju URL-a)."""
    return conn.execute(
        "SELECT * FROM games WHERE url LIKE ? ORDER BY end_time DESC", (f"%/{gid}",)
    ).fetchone()


def reset_interrupted(conn: sqlite3.Connection) -> int:
    """Partije ostale u statusu 'running' (prekinut proces) vraća na 'pending'."""
    with conn:
        cur = conn.execute(
            "UPDATE games SET analysis_status = 'pending' WHERE analysis_status = 'running'"
        )
    return cur.rowcount


def list_games_by_status(conn: sqlite3.Connection, statuses: tuple[str, ...]) -> list[sqlite3.Row]:
    """Partije sa datim statusom analize, od najstarije ka najnovijoj."""
    placeholders = ", ".join("?" for _ in statuses)
    return conn.execute(
        f"SELECT * FROM games WHERE analysis_status IN ({placeholders}) ORDER BY end_time",
        statuses,
    ).fetchall()


def set_status(conn: sqlite3.Connection, url: str, status: str) -> None:
    conn.execute("UPDATE games SET analysis_status = ? WHERE url = ?", (status, url))


MOVE_FIELDS = (
    "game_url", "ply", "move_number", "color", "fen_before", "move_san", "move_uci",
    "eval_before_cp", "eval_before_mate", "eval_after_cp", "eval_after_mate",
    "best_move_san", "best_move_uci", "pv",
    "second_best_uci", "second_eval_cp", "second_eval_mate", "classification",
)


def save_moves(conn: sqlite3.Connection, game_url: str, moves: list[dict]) -> None:
    """Zamenjuje analizu poteza za partiju (stari redovi se brišu)."""
    conn.execute("DELETE FROM moves WHERE game_url = ?", (game_url,))
    columns = ", ".join(MOVE_FIELDS)
    placeholders = ", ".join(f":{f}" for f in MOVE_FIELDS)
    conn.executemany(
        f"INSERT INTO moves ({columns}) VALUES ({placeholders})",
        [{**{f: m.get(f) for f in MOVE_FIELDS}, "game_url": game_url} for m in moves],
    )


def get_moves(conn: sqlite3.Connection, game_url: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM moves WHERE game_url = ? ORDER BY ply", (game_url,)
    ).fetchall()


def save_classifications(conn: sqlite3.Connection, game_url: str, labels: dict[int, str]) -> None:
    """Upisuje oznake poteza: {ply: oznaka}."""
    conn.executemany(
        "UPDATE moves SET classification = ? WHERE game_url = ? AND ply = ?",
        [(label, game_url, ply) for ply, label in labels.items()],
    )


def set_accuracy(conn: sqlite3.Connection, url: str, white: float | None, black: float | None) -> None:
    conn.execute(
        "UPDATE games SET white_accuracy = ?, black_accuracy = ? WHERE url = ?",
        (white, black, url),
    )
