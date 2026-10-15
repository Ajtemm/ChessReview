"""Win% i tačnost (Lichess formule)."""

import pytest

from app.analysis.scoring import CP_CEILING, game_accuracy, move_accuracy, white_cp, win_percent


def test_win_percent_je_50_za_jednaku_poziciju_i_simetrican():
    assert win_percent(0) == pytest.approx(50)
    assert win_percent(300) + win_percent(-300) == pytest.approx(100)
    assert win_percent(100) == pytest.approx(59.1, abs=0.1)


def test_win_percent_raste_sa_ocenom():
    values = [win_percent(cp) for cp in (-1000, -300, 0, 300, 1000)]
    assert values == sorted(values)


def test_white_cp_sece_ocenu_i_racuna_mat_kao_granicu():
    assert white_cp(5000, None, "white") == CP_CEILING
    assert white_cp(-5000, None, "black") == -CP_CEILING
    assert white_cp(None, 3, "white") == CP_CEILING
    assert white_cp(None, -2, "white") == -CP_CEILING


def test_mat_na_tabli_ide_u_korist_onoga_ko_je_odigrao_potez():
    assert white_cp(None, 0, "white") == CP_CEILING
    assert white_cp(None, 0, "black") == -CP_CEILING


def test_tacnost_poteza():
    assert move_accuracy(60, 60) == 100
    assert move_accuracy(60, 70) == 100  # popravljena pozicija se ne kažnjava
    assert move_accuracy(60, 55) > move_accuracy(60, 40) > move_accuracy(60, 10)
    assert 0 <= move_accuracy(100, 0) <= 100


def test_tacnost_partije_bez_gresaka_je_100():
    acc = game_accuracy([50.0] * 21)
    assert acc["white"] == pytest.approx(100)
    assert acc["black"] == pytest.approx(100)


def test_greska_belog_smanjuje_samo_tacnost_belog():
    # Posle 5. polupoteza (potez belog) win% belog pada sa 50 na 20 i tako ostaje
    wins = [50.0] * 5 + [20.0] * 16
    acc = game_accuracy(wins)
    assert acc["white"] < 90
    assert acc["black"] == pytest.approx(100)


def test_tacnost_prazne_partije():
    assert game_accuracy([50.0]) == {"white": None, "black": None}
