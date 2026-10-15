"""Podaci za UI: red u listi partija i sve za Review ekran jedne partije."""

import io
import sqlite3

import chess
import chess.pgn

from app import db
from app.analysis.scoring import white_win_percent


def outcome(result: str, my_color: str) -> str:
    """Rezultat iz mog ugla: 'win', 'loss' ili 'draw'."""
    if result == "1/2-1/2":
        return "draw"
    white_won = result == "1-0"
    return "win" if white_won == (my_color == "white") else "loss"


def game_summary(row: sqlite3.Row) -> dict:
    """Red u listi partija, iz mog ugla (protivnik, moja boja, moja tačnost...)."""
    me_white = row["my_color"] == "white"
    return {
        "id": db.game_id(row["url"]),
        "url": row["url"],
        "opponent": row["black"] if me_white else row["white"],
        "opponent_rating": row["black_rating"] if me_white else row["white_rating"],
        "my_rating": row["white_rating"] if me_white else row["black_rating"],
        "my_color": row["my_color"],
        "result": row["result"],
        "outcome": outcome(row["result"], row["my_color"]),
        "end_time": row["end_time"],
        "time_control": row["time_control"],
        "time_class": row["time_class"],
        "my_accuracy": row["white_accuracy"] if me_white else row["black_accuracy"],
        "opponent_accuracy": row["black_accuracy"] if me_white else row["white_accuracy"],
        "status": row["analysis_status"],
    }


def _position(board: chess.Board, last_move: str | None,
              cp: int | None, mate: int | None, mover: str) -> dict:
    """Pozicija za Review: FEN, ko je na potezu, šah, poslednji potez i ocena (ako postoji)."""
    has_eval = cp is not None or mate is not None
    return {
        "fen": board.fen(),
        "turn": "white" if board.turn == chess.WHITE else "black",
        "check": board.is_check(),
        "last_move": last_move,
        "cp": cp,
        "mate": mate,
        "win": white_win_percent(cp, mate, mover) if has_eval else None,
    }


def review_positions_and_moves(pgn: str, analysis: dict[int, sqlite3.Row]) -> dict:
    """Pozicije (FEN + ocena) i potezi za Review ekran.

    Pozicije i potezi se prave iz PGN-a, pa ekran radi i pre nego što je analiza
    gotova; ocene i oznake se dodaju iz tabele moves (`analysis`: {ply: red}) kad postoje.
    `positions[k]` je pozicija posle k-tog polupoteza (0 = početna).
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()

    # Početna pozicija: ocena pre prvog poteza
    first = analysis.get(1)
    positions = [_position(board, None,
                           first["eval_before_cp"] if first else None,
                           first["eval_before_mate"] if first else None, "white")]
    moves = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        row = analysis.get(ply)
        color = "white" if board.turn == chess.WHITE else "black"
        moves.append({
            "ply": ply,
            "move_number": board.fullmove_number,
            "color": color,
            "san": board.san(move),
            "uci": move.uci(),
            "capture": board.is_capture(move),
            "classification": row["classification"] if row else None,
            "best_san": row["best_move_san"] if row else None,
            "best_uci": row["best_move_uci"] if row else None,
            "pv": row["pv"] if row else None,
        })
        board.push(move)
        positions.append(_position(board, move.uci(),
                                   row["eval_after_cp"] if row else None,
                                   row["eval_after_mate"] if row else None, color))
    return {"positions": positions, "moves": moves}


def review_payload(game: sqlite3.Row, analysis_rows: list[sqlite3.Row]) -> dict:
    """Sve za Review jedne partije: podaci o partiji (obe strane), pozicije i potezi."""
    summary = game_summary(game)
    for side in ("white", "black"):
        summary[side] = game[side]
        summary[f"{side}_rating"] = game[f"{side}_rating"]
        summary[f"{side}_accuracy"] = game[f"{side}_accuracy"]
    analysis = {m["ply"]: m for m in analysis_rows}
    return {"game": summary, **review_positions_and_moves(game["pgn"], analysis)}
