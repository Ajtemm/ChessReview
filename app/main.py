"""FastAPI aplikacija: API za partije, statičke stranice i analiza u pozadini."""

import io
import logging
import threading
from contextlib import asynccontextmanager

import chess
import chess.pgn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import analyzer, db
from app.config import ROOT_DIR, load_config

STATIC_DIR = ROOT_DIR / "static"

# Uvicorn-ov logger, da se poruke vide u istom izlazu kao i server
log = logging.getLogger("uvicorn.error")


class AnalysisWorker:
    """Pozadinska nit koja analizira nove partije (status 'pending').

    Budi se na `trigger()` (npr. posle preuzimanja) ili posle `poll_seconds`,
    pa vidi i partije koje je ubacio fetcher pokrenut iz komandne linije.
    """

    def __init__(self, poll_seconds: float):
        self.poll_seconds = poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="analysis-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def trigger(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        # Partija koja se upravo analizira se završava; ne čekamo predugo
        self._thread.join(timeout=10)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                # Partije sa greškom ne pokušavamo stalno; za njih je komanda analyzer-a
                stats = analyzer.analyze_pending(("pending",), should_stop=self._stop.is_set)
                if stats["done"] or stats["error"]:
                    log.info("Analiza u pozadini: %s", stats)
            except Exception:
                log.exception("Greška u pozadinskoj analizi")
            self._wake.wait(self.poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    try:
        # Analize prekinute gašenjem servera vraćamo u red
        db.reset_interrupted(conn)
    finally:
        conn.close()

    config = load_config()
    worker = AnalysisWorker(float(config.get("analysis_poll_seconds", 60)))
    app.state.worker = worker
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Chess Review", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _outcome(result: str, my_color: str) -> str:
    """Rezultat iz mog ugla: 'win', 'loss' ili 'draw'."""
    if result == "1/2-1/2":
        return "draw"
    white_won = result == "1-0"
    return "win" if white_won == (my_color == "white") else "loss"


def _game_summary(row) -> dict:
    me_white = row["my_color"] == "white"
    return {
        "id": db.game_id(row["url"]),
        "url": row["url"],
        "opponent": row["black"] if me_white else row["white"],
        "opponent_rating": row["black_rating"] if me_white else row["white_rating"],
        "my_rating": row["white_rating"] if me_white else row["black_rating"],
        "my_color": row["my_color"],
        "result": row["result"],
        "outcome": _outcome(row["result"], row["my_color"]),
        "end_time": row["end_time"],
        "time_control": row["time_control"],
        "time_class": row["time_class"],
        "my_accuracy": row["white_accuracy"] if me_white else row["black_accuracy"],
        "opponent_accuracy": row["black_accuracy"] if me_white else row["white_accuracy"],
        "status": row["analysis_status"],
    }


# Obične (ne async) rute FastAPI izvršava u posebnim nitima, pa SQLite ne blokira server
@app.get("/api/games")
def api_games() -> list[dict]:
    conn = db.connect()
    try:
        return [_game_summary(r) for r in db.list_games(conn)]
    finally:
        conn.close()


def _review_data(pgn: str, analysis: dict[int, dict]) -> dict:
    """Pozicije (FEN + ocena) i potezi za Review ekran.

    Pozicije i potezi se prave iz PGN-a, pa ekran radi i pre nego što je analiza
    gotova; ocene i oznake se dodaju iz tabele moves kad postoje.
    `positions[k]` je pozicija posle k-tog polupoteza (0 = početna).
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()

    def position(last_move: str | None, row, cp_key: str, mate_key: str, mover: str) -> dict:
        has_eval = row is not None and (row[cp_key] is not None or row[mate_key] is not None)
        return {
            "fen": board.fen(),
            "turn": "white" if board.turn == chess.WHITE else "black",
            "check": board.is_check(),
            "last_move": last_move,
            "cp": row[cp_key] if row else None,
            "mate": row[mate_key] if row else None,
            "win": analyzer.white_win_percent(row[cp_key], row[mate_key], mover) if has_eval else None,
        }

    # Početna pozicija: ocena pre prvog poteza
    positions = [position(None, analysis.get(1), "eval_before_cp", "eval_before_mate", "white")]
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
            "classification": row["classification"] if row else None,
            "best_san": row["best_move_san"] if row else None,
            "best_uci": row["best_move_uci"] if row else None,
            "pv": row["pv"] if row else None,
        })
        board.push(move)
        positions.append(position(move.uci(), row, "eval_after_cp", "eval_after_mate", color))
    return {"positions": positions, "moves": moves}


@app.get("/api/games/{gid}")
def api_game(gid: str) -> dict:
    """Sve za Review jedne partije: podaci o partiji, pozicije sa ocenama i potezi."""
    conn = db.connect()
    try:
        game = db.get_game_by_id(conn, gid)
        if game is None:
            raise HTTPException(status_code=404, detail="Partija nije pronađena")
        analysis = {m["ply"]: m for m in db.get_moves(conn, game["url"])}
    finally:
        conn.close()

    summary = _game_summary(game)
    summary.update({
        "white": game["white"],
        "black": game["black"],
        "white_rating": game["white_rating"],
        "black_rating": game["black_rating"],
        "white_accuracy": game["white_accuracy"],
        "black_accuracy": game["black_accuracy"],
    })
    return {"game": summary, **_review_data(game["pgn"], analysis)}


@app.get("/")
def index_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/review/{gid}")
def review_page(gid: str):
    conn = db.connect()
    try:
        game = db.get_game_by_id(conn, gid)
    finally:
        conn.close()
    if game is None:
        raise HTTPException(status_code=404, detail="Partija nije pronađena")
    return FileResponse(STATIC_DIR / "review.html")
