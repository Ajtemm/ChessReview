"""Preuzimanje poslednjih partija sa Chess.com javnog API-ja."""

import time
from datetime import datetime, timezone

import requests

from app import db
from app.config import load_config

API_BASE = "https://api.chess.com/pub/player"

# Chess.com rezultati koji znače remi
DRAW_RESULTS = {
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient",
}


class ChessComClient:
    """Mali klijent sa User-Agent zaglavljem i pauzom između zahteva."""

    def __init__(self, contact: str, delay: float = 1.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"chess-review/0.1 (contact: {contact})"

    def get(self, url: str) -> dict:
        for attempt in range(1, self.max_retries + 1):
            # Pauza između zahteva da ne opterećujemo API
            wait = self.delay - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

            resp = self.session.get(url, timeout=30)
            if resp.status_code == 429 and attempt < self.max_retries:
                # Previše zahteva: čekamo duže pa pokušavamo ponovo
                time.sleep(self.delay * 5 * attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Neuspešan zahtev: {url}")


def _result_string(raw: dict) -> str:
    """Pretvara chess.com rezultate u '1-0', '0-1' ili '1/2-1/2'."""
    if raw["white"]["result"] == "win":
        return "1-0"
    if raw["black"]["result"] == "win":
        return "0-1"
    return "1/2-1/2"


def parse_game(raw: dict, username: str) -> dict | None:
    """Pretvara chess.com zapis u red za bazu. Vraća None za nepodržane partije."""
    # Analiziramo samo standardni šah, bez varijanti (chess960 i sl.)
    if raw.get("rules") != "chess" or not raw.get("pgn"):
        return None

    white = raw["white"]["username"]
    black = raw["black"]["username"]
    if white.lower() == username.lower():
        my_color = "white"
    elif black.lower() == username.lower():
        my_color = "black"
    else:
        return None

    end_time = datetime.fromtimestamp(raw["end_time"], tz=timezone.utc)
    return {
        "url": raw["url"],
        "uuid": raw.get("uuid"),
        "pgn": raw["pgn"],
        "white": white,
        "black": black,
        "white_rating": raw["white"].get("rating"),
        "black_rating": raw["black"].get("rating"),
        "result": _result_string(raw),
        "my_color": my_color,
        "end_time": end_time.isoformat(timespec="seconds"),
        "time_control": raw.get("time_control"),
        "time_class": raw.get("time_class"),
    }


def fetch_recent_games(client: ChessComClient, username: str, limit: int) -> list[dict]:
    """Vraća do `limit` poslednjih partija, od najnovije ka starijoj."""
    archives = client.get(f"{API_BASE}/{username.lower()}/games/archives")["archives"]

    games: list[dict] = []
    # Arhive su mesečne i poređane od najstarije; idemo unazad dok ne skupimo dovoljno
    for archive_url in reversed(archives):
        month_games = client.get(archive_url).get("games", [])
        month_games.sort(key=lambda g: g.get("end_time", 0), reverse=True)
        for raw in month_games:
            parsed = parse_game(raw, username)
            if parsed:
                games.append(parsed)
                if len(games) >= limit:
                    return games
    return games


def fetch_and_store() -> dict:
    """Preuzima poslednje partije i čuva samo nove. Vraća statistiku."""
    config = load_config()
    username = config["chesscom_username"]
    client = ChessComClient(
        contact=config["contact_email"],
        delay=float(config.get("request_delay_seconds", 1.0)),
    )

    games = fetch_recent_games(client, username, int(config.get("games_to_fetch", 20)))

    with db.connection() as conn:
        with conn:
            new = sum(db.insert_game(conn, g) for g in games)
        total = db.count_games(conn)

    return {"fetched": len(games), "new": new, "total": total}
