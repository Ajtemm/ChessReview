"""FastAPI aplikacija: rute za API i stranice; posao u pozadini je u app/background.py."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.background import BackgroundServices
from app.config import ROOT_DIR, load_config
from app.review_data import game_summary, review_payload

STATIC_DIR = ROOT_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = BackgroundServices(load_config())
    app.state.services = services
    services.start()
    yield
    services.stop()


app = FastAPI(title="Chess Review", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _game_or_404(conn, gid: str):
    game = db.get_game_by_id(conn, gid)
    if game is None:
        raise HTTPException(status_code=404, detail="Partija nije pronađena")
    return game


# Obične (ne async) rute FastAPI izvršava u posebnim nitima, pa SQLite ne blokira server

@app.get("/api/games")
def api_games() -> list[dict]:
    """Lista partija, od najnovije."""
    with db.connection() as conn:
        return [game_summary(row) for row in db.list_games(conn)]


@app.get("/api/games/{gid}")
def api_game(gid: str) -> dict:
    """Sve za Review jedne partije: podaci o partiji, pozicije sa ocenama i potezi."""
    with db.connection() as conn:
        game = _game_or_404(conn, gid)
        moves = db.get_moves(conn, game["url"])
    return review_payload(game, moves)


@app.get("/api/status")
def api_status() -> dict:
    """Stanje preuzimanja i analize u pozadini."""
    return app.state.services.status()


@app.post("/api/fetch")
def api_fetch() -> dict:
    """Ručno pokretanje preuzimanja (dugme). Ne čeka kraj; napredak je u /api/status."""
    started = app.state.services.fetch.start_in_background()
    return {"started": started, **app.state.services.status()}


@app.get("/")
def index_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/review/{gid}")
def review_page(gid: str):
    with db.connection() as conn:
        _game_or_404(conn, gid)
    return FileResponse(STATIC_DIR / "review.html")
