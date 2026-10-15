"""Analiza partija iz baze (Stockfish + oznake poteza) i komande za komandnu liniju.

    python -m app.analyzer                 analiziraj sve partije koje čekaju (pending/error)
    python -m app.analyzer --game URL      analiziraj jednu partiju
    python -m app.analyzer --show URL      tabela poteza sa ocenama i oznakama
    python -m app.analyzer --classify      ponovo izračunaj oznake i tačnost (bez Stockfish-a)
    python -m app.analyzer --stats         broj poteza po oznakama
"""

import argparse
import sqlite3
from collections import Counter
from collections.abc import Callable

import chess.engine

from app import db
from app.classify import classify_moves
from app.config import load_config, resolve_path
from app.engine import analyze_moves, open_engine
from app.openings import load_book

# Statusi partija koje komanda bez argumenata (ponovo) analizira
TO_ANALYZE = ("pending", "error")

LABEL_ORDER = ("brilliant", "great", "best", "excellent", "good", "book",
               "inaccuracy", "mistake", "miss", "blunder")


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


# ---------------------------------------------------------------- ispis

def format_eval(cp: int | None, mate: int | None) -> str:
    """Ocena za prikaz: +0.35, #3, #-2, ili # kad je mat na tabli."""
    if mate is not None:
        return "#" if mate == 0 else f"#{mate}"
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


def print_moves(conn: sqlite3.Connection, url: str, pv_len: int = 5) -> None:
    """Ispisuje tabelu poteza sa ocenama i oznakama za jednu partiju."""
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")
    print(f"{game['white']} - {game['black']}  {game['result']}  ({game['time_control']}, {game['end_time'][:10]})")
    if game["white_accuracy"] is not None:
        print(f"Tačnost: beli {game['white_accuracy']:.1f}, crni {game['black_accuracy']:.1f}")
    print(f"{'Potez':>7}  {'SAN':<8} {'Pre':>7} {'Posle':>7}  {'Oznaka':<11} {'Najbolji':<8} Varijanta")
    for m in db.get_moves(conn, url):
        num = f"{m['move_number']}." if m["color"] == "white" else f"{m['move_number']}..."
        pv = " ".join((m["pv"] or "").split()[:pv_len])
        print(
            f"{num:>7}  {m['move_san']:<8} "
            f"{format_eval(m['eval_before_cp'], m['eval_before_mate']):>7} "
            f"{format_eval(m['eval_after_cp'], m['eval_after_mate']):>7}  "
            f"{m['classification'] or '-':<11} {m['best_move_san'] or '-':<8} {pv}"
        )


def print_stats() -> None:
    """Broj poteza po oznakama za sve analizirane partije: moji, protivnikovi, ukupno."""
    with db.connection() as conn:
        counts = db.label_counts(conn)
        n_games = len(db.list_games_by_status(conn, ("done",)))

    print(f"Analiziranih partija: {n_games}")
    print(f"{'Oznaka':<11} {'Ja':>5} {'Protivnik':>10} {'Ukupno':>7}")
    for label in LABEL_ORDER:
        mine, theirs = counts.get((label, True), 0), counts.get((label, False), 0)
        print(f"{label:<11} {mine:>5} {theirs:>10} {mine + theirs:>7}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stockfish analiza partija iz baze")
    parser.add_argument("--game", metavar="URL", help="analiziraj samo ovu partiju")
    parser.add_argument("--show", metavar="URL", help="prikaži tabelu poteza za partiju")
    parser.add_argument("--classify", action="store_true",
                        help="ponovo izračunaj oznake i tačnost za analizirane partije")
    parser.add_argument("--stats", action="store_true", help="broj poteza po oznakama")
    args = parser.parse_args()

    if args.classify:
        print(f"Oznake izračunate za {classify_all()} partija")
    elif args.stats:
        print_stats()
    elif args.game:
        with db.connection() as conn:
            plies = analyze_game(conn, args.game)
        print(f"Analizirano {plies} polupoteza")
    elif args.show:
        with db.connection() as conn:
            print_moves(conn, args.show)
    else:
        stats = analyze_pending()
        print(f"Analizirano: {stats['done']}, grešaka: {stats['error']}")


if __name__ == "__main__":
    main()
