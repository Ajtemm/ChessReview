"""Podaci za UI: rezultat iz mog ugla i pozicije/potezi za Review ekran."""

import pytest

from app.review_data import outcome, review_positions_and_moves

# Školski mat: 7 polupoteza, poslednji je uzimanje sa matom
SCHOLARS_MATE = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


@pytest.mark.parametrize("result, my_color, expected", [
    ("1-0", "white", "win"), ("1-0", "black", "loss"),
    ("0-1", "black", "win"), ("1/2-1/2", "white", "draw"),
])
def test_outcome(result, my_color, expected):
    assert outcome(result, my_color) == expected


def test_review_bez_analize_ima_pozicije_i_poteze_ali_bez_ocena():
    data = review_positions_and_moves(SCHOLARS_MATE, {})
    positions, moves = data["positions"], data["moves"]
    assert len(positions) == len(moves) + 1 == 8
    assert positions[0]["last_move"] is None
    assert moves[-1]["san"] == "Qxf7#" and moves[-1]["capture"]
    assert positions[-1]["check"] and positions[-1]["turn"] == "black"
    assert all(p["win"] is None for p in positions)
    assert all(m["classification"] is None for m in moves)


def test_review_sa_analizom_racuna_win_i_mat_na_tabli():
    rows = {}
    for ply in range(1, 8):
        rows[ply] = {
            "eval_before_cp": 20, "eval_before_mate": None,
            "eval_after_cp": 20 if ply < 7 else None,
            "eval_after_mate": 0 if ply == 7 else None,
            "classification": "best", "best_move_san": None, "best_move_uci": None, "pv": None,
        }
    data = review_positions_and_moves(SCHOLARS_MATE, rows)
    assert data["positions"][0]["win"] == pytest.approx(51.8, abs=0.1)
    assert data["positions"][-1]["win"] > 97  # mat koji je dao beli
    assert data["moves"][0]["classification"] == "best"
