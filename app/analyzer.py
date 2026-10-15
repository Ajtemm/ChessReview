"""Analiza partija Stockfish-om: ocena svake pozicije, najbolji potez i varijanta."""

import argparse
import io
import sqlite3

import chess
import chess.engine
import chess.pgn

from app import db
from app.config import load_config

# Statusi partija koje treba (ponovo) analizirati
TO_ANALYZE = ("pending", "error")


def open_engine(config: dict) -> chess.engine.SimpleEngine:
    """Pokreće Stockfish sa putanje iz config.json."""
    return chess.engine.SimpleEngine.popen_uci(config["stockfish_path"])


def _score_fields(score: chess.engine.Score) -> tuple[int | None, int | None]:
    """Vraća (centipešaci, mat) iz ugla belog; jedno od dva je uvek None."""
    mate = score.mate()
    if mate is not None:
        return None, mate
    return score.score(), None


def _evaluate(
    engine: chess.engine.SimpleEngine, board: chess.Board, depth: int
) -> dict:
    """Ocena jedne pozicije, najbolji potez i glavna varijanta."""
    # Završne pozicije ocenjujemo bez engine-a
    if board.is_checkmate():
        # Mat 0: mat je na tabli, pobedio je onaj ko je odigrao poslednji potez
        return {"cp": None, "mate": 0, "best_uci": None, "best_san": None, "pv": None}
    if board.is_stalemate() or board.is_insufficient_material():
        return {"cp": 0, "mate": None, "best_uci": None, "best_san": None, "pv": None}

    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    cp, mate = _score_fields(info["score"].white())

    pv_moves = info.get("pv") or []
    pv_san = []
    tmp = board.copy(stack=False)
    for move in pv_moves:
        pv_san.append(tmp.san(move))
        tmp.push(move)

    best = pv_moves[0] if pv_moves else None
    return {
        "cp": cp,
        "mate": mate,
        "best_uci": best.uci() if best else None,
        "best_san": pv_san[0] if pv_san else None,
        "pv": " ".join(pv_san) or None,
    }


def analyze_moves(pgn: str, engine: chess.engine.SimpleEngine, depth: int) -> list[dict]:
    """Prolazi kroz sve poteze partije i vraća redove za tabelu moves."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("PGN nije moguće pročitati")

    board = game.board()
    # Ocena posle poteza N je ocena pre poteza N+1, pa svaku poziciju analiziramo jednom
    current = _evaluate(engine, board, depth)

    rows = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        row = {
            "ply": ply,
            "move_number": board.fullmove_number,
            "color": "white" if board.turn == chess.WHITE else "black",
            "fen_before": board.fen(),
            "move_san": board.san(move),
            "move_uci": move.uci(),
            "eval_before_cp": current["cp"],
            "eval_before_mate": current["mate"],
            "best_move_san": current["best_san"],
            "best_move_uci": current["best_uci"],
            "pv": current["pv"],
        }
        board.push(move)
        current = _evaluate(engine, board, depth)
        row["eval_after_cp"] = current["cp"]
        row["eval_after_mate"] = current["mate"]
        rows.append(row)
    return rows


def analyze_game(
    conn: sqlite3.Connection,
    url: str,
    engine: chess.engine.SimpleEngine | None = None,
    config: dict | None = None,
) -> int:
    """Analizira jednu partiju iz baze i čuva rezultate. Vraća broj polupoteza."""
    config = config or load_config()
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")

    with conn:
        db.set_status(conn, url, "running")

    own_engine = engine is None
    if own_engine:
        engine = open_engine(config)
    try:
        rows = analyze_moves(game["pgn"], engine, int(config["analysis_depth"]))
        with conn:
            db.save_moves(conn, url, rows)
            db.set_status(conn, url, "done")
        return len(rows)
    except KeyboardInterrupt:
        # Prekinuto ručno: vraćamo partiju u red za analizu
        with conn:
            db.set_status(conn, url, "pending")
        raise
    except Exception:
        with conn:
            db.set_status(conn, url, "error")
        raise
    finally:
        if own_engine:
            engine.quit()


def analyze_pending() -> dict:
    """Analizira sve partije koje još nisu analizirane. Vraća statistiku."""
    config = load_config()
    conn = db.connect()
    engine = open_engine(config)
    stats = {"done": 0, "error": 0}
    try:
        games = db.list_games_by_status(conn, TO_ANALYZE)
        for i, game in enumerate(games, start=1):
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
        conn.close()
    return stats


def format_eval(cp: int | None, mate: int | None) -> str:
    """Ocena za prikaz: +0.35, #3, #-2, ili # kad je mat na tabli."""
    if mate is not None:
        return "#" if mate == 0 else f"#{mate}"
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


def print_moves(conn: sqlite3.Connection, url: str, pv_len: int = 5) -> None:
    """Ispisuje tabelu poteza sa ocenama za jednu partiju."""
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")
    print(f"{game['white']} - {game['black']}  {game['result']}  ({game['time_control']}, {game['end_time'][:10]})")
    print(f"{'Potez':>7}  {'SAN':<8} {'Pre':>7} {'Posle':>7}  {'Najbolji':<8} Varijanta")
    for m in db.get_moves(conn, url):
        num = f"{m['move_number']}." if m["color"] == "white" else f"{m['move_number']}..."
        pv = " ".join((m["pv"] or "").split()[:pv_len])
        print(
            f"{num:>7}  {m['move_san']:<8} "
            f"{format_eval(m['eval_before_cp'], m['eval_before_mate']):>7} "
            f"{format_eval(m['eval_after_cp'], m['eval_after_mate']):>7}  "
            f"{m['best_move_san'] or '-':<8} {pv}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stockfish analiza partija iz baze")
    parser.add_argument("--game", metavar="URL", help="analiziraj samo ovu partiju")
    parser.add_argument("--show", metavar="URL", help="prikaži tabelu poteza za partiju")
    args = parser.parse_args()

    if args.game:
        conn = db.connect()
        try:
            plies = analyze_game(conn, args.game)
            print(f"Analizirano {plies} polupoteza")
        finally:
            conn.close()
    elif args.show:
        conn = db.connect()
        try:
            print_moves(conn, args.show)
        finally:
            conn.close()
    else:
        stats = analyze_pending()
        print(f"Analizirano: {stats['done']}, grešaka: {stats['error']}")


if __name__ == "__main__":
    main()
