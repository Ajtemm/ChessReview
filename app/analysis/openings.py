"""Knjiga otvaranja (oznaka Book) iz lokalne lichess chess-openings baze (TSV)."""

import csv
from pathlib import Path

import chess

# Gotov skup pozicija na disku: pravljenje iz TSV-a traje ~3 s i drži GIL,
# pa bi usporilo server dok se analiza vrti u pozadini
BOOK_CACHE_NAME = "book_cache.epd"

_book_cache: dict[Path, set[str]] = {}


def _build_book(tsv_files: list[Path]) -> set[str]:
    positions: set[str] = set()
    for path in tsv_files:
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                board = chess.Board()
                for token in row["pgn"].split():
                    if token[0].isdigit():  # broj poteza, npr. "1."
                        continue
                    board.push_san(token)
                    positions.add(board.epd())
    return positions


def load_book(openings_dir: Path) -> set[str]:
    """Skup pozicija (EPD) iz TSV fajlova, uključujući međupozicije svake varijante."""
    if openings_dir in _book_cache:
        return _book_cache[openings_dir]
    tsv_files = sorted(openings_dir.glob("*.tsv"))
    if not tsv_files:
        raise FileNotFoundError(f"Nema TSV fajlova otvaranja u {openings_dir}")

    cache = openings_dir / BOOK_CACHE_NAME
    newest_tsv = max(p.stat().st_mtime for p in tsv_files)
    if cache.exists() and cache.stat().st_mtime >= newest_tsv:
        positions = set(cache.read_text(encoding="utf-8").splitlines())
    else:
        positions = _build_book(tsv_files)
        cache.write_text("\n".join(sorted(positions)), encoding="utf-8")
    _book_cache[openings_dir] = positions
    return positions
