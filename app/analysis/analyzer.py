"""Analiza partija iz baze: Stockfish, pa oznake poteza i tačnost; rezultati idu u bazu."""

import sqlite3
from collections import Counter
from collections.abc import Callable

import chess.engine

from app import db
from app.analysis.classify import classify_moves
from app.analysis.engine import analyze_moves, open_engine
from app.analysis.openings import load_book
from app.config import load_config, resolve_path

# Statusi partija koje komanda bez argumenata (ponovo) analizira
TO_ANALYZE = ("pending", "error")


# ---------------------------------------------------------------- oznake

def classify_game(conn: sqlite3.Connection, url: str, config: dict | None = None) -> Counter:
    """Računa i čuva oznake poteza i tačnost za već analiziranu partiju (bez Stockfish-a)."""
    config = config or load_config()
    book = load_book(resolve_path(config["openings_dir"]))
    labels, accuracy = classify_moves(db.get_moves(conn, url), book)
    with conn:
        db.save_classifications(conn, url, labels)
        db.set_accuracy(conn, url, accuracy["white"], accuracy["black"])
    return Counter(labels.values())


def classify_all() -> int:
    """Ponovo računa oznake za sve analizirane partije. Vraća broj partija."""
    config = load_config()
    with db.connection() as conn:
        games = db.list_games_by_status(conn, ("done",))
        for game in games:
            classify_game(conn, game["url"], config)
    return len(games)


# ---------------------------------------------------------------- analiza

def analyze_game(
    conn: sqlite3.Connection,
    url: str,
    engine: chess.engine.SimpleEngine | None = None,
    config: dict | None = None,
) -> int:
    """Analizira jednu partiju iz baze, čuva poteze, oznake i tačnost. Vraća broj polupoteza.

    Bez prosleđenog `engine`-a sama pokreće i gasi Stockfish.
    """
    config = config or load_config()
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")

    def set_status(status: str) -> None:
        with conn:
            db.set_status(conn, url, status)

    set_status("running")
    own_engine = engine is None
    if own_engine:
        engine = open_engine(config)
    try:
        rows = analyze_moves(game["pgn"], engine, int(config["analysis_depth"]))
        with conn:
            db.save_moves(conn, url, rows)
        classify_game(conn, url, config)
        set_status("done")
        return len(rows)
    except KeyboardInterrupt:
        # Prekinuto ručno: vraćamo partiju u red za analizu
        set_status("pending")
        raise
    except Exception:
        set_status("error")
        raise
    finally:
        if own_engine:
            engine.quit()


def analyze_pending(
    statuses: tuple[str, ...] = TO_ANALYZE,
    should_stop: Callable[[], bool] = lambda: False,
    on_progress: Callable[[int, int], None] = lambda current, total: None,
) -> dict:
    """Analizira sve partije sa datim statusom. Vraća {"done": n, "error": n}.

    `should_stop` se proverava između partija (za gašenje servera), a
    `on_progress(trenutna, ukupno)` se poziva pre svake partije (za prikaz u UI-ju).
    """
    stats = {"done": 0, "error": 0}
    with db.connection() as conn:
        games = db.list_games_by_status(conn, statuses)
        if not games:
            return stats

        config = load_config()
        engine = open_engine(config)
        try:
            for i, game in enumerate(games, start=1):
                if should_stop():
                    break
                on_progress(i, len(games))
                label = f"[{i}/{len(games)}] {game['white']} - {game['black']} ({game['end_time'][:10]})"
                try:
                    plies = analyze_game(conn, game["url"], engine=engine, config=config)
                    stats["done"] += 1
                    print(f"{label}: {plies} polupoteza")
                except Exception as e:
                    stats["error"] += 1
                    print(f"{label}: GREŠKA {e}")
        finally:
            engine.quit()
    return stats
