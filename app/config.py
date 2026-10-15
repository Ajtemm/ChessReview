"""Učitavanje podešavanja iz config.json."""

import json
from pathlib import Path

# Koren projekta (folder u kome je config.json)
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"


def load_config() -> dict:
    """Vraća podešavanja iz config.json kao rečnik."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def resolve_path(path: str) -> Path:
    """Relativne putanje iz config-a tumačimo u odnosu na koren projekta."""
    p = Path(path)
    return p if p.is_absolute() else ROOT_DIR / p
