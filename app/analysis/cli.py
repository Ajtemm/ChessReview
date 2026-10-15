"""Komande za analizu iz komandne linije.

    python -m app.analysis                 analiziraj sve partije koje čekaju (pending/error)
    python -m app.analysis --game URL      analiziraj jednu partiju
    python -m app.analysis --show URL      tabela poteza sa ocenama i oznakama
    python -m app.analysis --classify      ponovo izračunaj oznake i tačnost (bez Stockfish-a)
    python -m app.analysis --stats         broj poteza po oznakama
"""

import argparse
import sqlite3

from app import db
from app.analysis.analyzer import analyze_game, analyze_pending, classify_all

LABEL_ORDER = ("brilliant", "great", "best", "excellent", "good", "book",
               "inaccuracy", "mistake", "miss", "blunder")


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
    parser = argparse.ArgumentParser(prog="python -m app.analysis",
                                     description="Stockfish analiza partija iz baze")
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
