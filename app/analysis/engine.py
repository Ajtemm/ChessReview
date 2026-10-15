"""Stockfish: ocena pozicija i prolaz kroz sve poteze partije."""

import io
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn


@dataclass
class PositionEval:
    """Ocena jedne pozicije iz ugla belog: tačno jedno od `cp` (centipešaci) i `mate` nije None.

    `mate` = 0 znači da je mat na tabli (pobedio je onaj ko je odigrao poslednji potez).
    """

    cp: int | None
    mate: int | None
    best_uci: str | None = None
    best_san: str | None = None
    pv: str | None = None              # glavna varijanta u SAN-u, potezi razdvojeni razmakom
    second_uci: str | None = None      # drugi najbolji potez (MultiPV 2), za oznaku Great
    second_cp: int | None = None
    second_mate: int | None = None


def open_engine(config: dict) -> chess.engine.SimpleEngine:
    """Pokreće Stockfish sa putanje iz config.json."""
    return chess.engine.SimpleEngine.popen_uci(config["stockfish_path"])


def score_fields(score: chess.engine.Score) -> tuple[int | None, int | None]:
    """Vraća (centipešaci, mat) za ocenu; jedno od dva je uvek None."""
    mate = score.mate()
    if mate is not None:
        return None, mate
    return score.score(), None


def _pv_to_san(board: chess.Board, moves: list[chess.Move]) -> list[str]:
    tmp = board.copy(stack=False)
    san = []
    for move in moves:
        san.append(tmp.san(move))
        tmp.push(move)
    return san


def evaluate_position(engine: chess.engine.SimpleEngine, board: chess.Board, depth: int) -> PositionEval:
    """Ocena pozicije, najbolji i drugi najbolji potez i glavna varijanta."""
    # Završne pozicije ocenjujemo bez engine-a
    if board.is_checkmate():
        return PositionEval(cp=None, mate=0)
    if board.is_stalemate() or board.is_insufficient_material():
        return PositionEval(cp=0, mate=None)

    # MultiPV 2: drugi najbolji potez treba za oznaku Great (jedini dobar potez)
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
    best = infos[0]
    cp, mate = score_fields(best["score"].white())
    pv_moves = best.get("pv") or []
    pv_san = _pv_to_san(board, pv_moves)
    result = PositionEval(
        cp=cp,
        mate=mate,
        best_uci=pv_moves[0].uci() if pv_moves else None,
        best_san=pv_san[0] if pv_san else None,
        pv=" ".join(pv_san) or None,
    )

    if len(infos) > 1 and infos[1].get("pv"):
        result.second_uci = infos[1]["pv"][0].uci()
        result.second_cp, result.second_mate = score_fields(infos[1]["score"].white())
    return result


def analyze_moves(pgn: str, engine: chess.engine.SimpleEngine, depth: int) -> list[dict]:
    """Prolazi kroz sve poteze partije i vraća redove za tabelu moves."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("PGN nije moguće pročitati")

    board = game.board()
    # Ocena posle poteza N je ocena pre poteza N+1, pa svaku poziciju analiziramo jednom
    current = evaluate_position(engine, board, depth)

    rows = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        row = {
            "ply": ply,
            "move_number": board.fullmove_number,
            "color": "white" if board.turn == chess.WHITE else "black",
            "fen_before": board.fen(),
            "move_san": board.san(move),
            "move_uci": move.uci(),
            "eval_before_cp": current.cp,
            "eval_before_mate": current.mate,
            "best_move_san": current.best_san,
            "best_move_uci": current.best_uci,
            "pv": current.pv,
            "second_best_uci": current.second_uci,
            "second_eval_cp": current.second_cp,
            "second_eval_mate": current.second_mate,
        }
        board.push(move)
        current = evaluate_position(engine, board, depth)
        row["eval_after_cp"] = current.cp
        row["eval_after_mate"] = current.mate
        rows.append(row)
    return rows
