"""Rute: API za partije i status, i HTML stranice (lista partija, Review)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app import db
from app.config import ROOT_DIR
from app.web.review_data import game_summary, review_payload

STATIC_DIR = ROOT_DIR / "static"

router = APIRouter()


def _game_or_404(conn, gid: str):
    game = db.get_game_by_id(conn, gid)
    if game is None:
        raise HTTPException(status_code=404, detail="Partija nije pronađena")
    return game


# Obične (ne async) rute FastAPI izvršava u posebnim nitima, pa SQLite ne blokira server

@router.get("/api/games")
def api_games() -> list[dict]:
    """Lista partija, od najnovije."""
    with db.connection() as conn:
        return [game_summary(row) for row in db.list_games(conn)]


@router.get("/api/games/{gid}")
def api_game(gid: str) -> dict:
    """Sve za Review jedne partije: podaci o partiji, pozicije sa ocenama i potezi."""
    with db.connection() as conn:
        game = _game_or_404(conn, gid)
        moves = db.get_moves(conn, game["url"])
    return review_payload(game, moves)


@router.get("/api/status")
def api_status(request: Request) -> dict:
    """Stanje preuzimanja i analize u pozadini."""
    return request.app.state.services.status()


@router.post("/api/fetch")
def api_fetch(request: Request) -> dict:
    """Ručno pokretanje preuzimanja (dugme). Ne čeka kraj; napredak je u /api/status."""
    services = request.app.state.services
    started = services.fetch.start_in_background()
    return {"started": started, **services.status()}


@router.get("/")
def index_page():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/review/{gid}")
def review_page(gid: str):
    with db.connection() as conn:
        _game_or_404(conn, gid)
    return FileResponse(STATIC_DIR / "review.html")
