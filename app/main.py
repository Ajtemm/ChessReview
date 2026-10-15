"""FastAPI aplikacija: API za partije, statičke stranice i analiza u pozadini."""

import logging
import threading
from contextlib import asynccontextmanager

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
