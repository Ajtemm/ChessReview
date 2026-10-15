"""Oznake poteza: pragovi pada win%, Book, Miss, Great, Brilliant i detekcija žrtve."""

import chess
import pytest

from app.classify import classify_moves, is_sacrifice, sacrifice_confirmed


def make_rows(specs: list[dict], start_fen: str = chess.STARTING_FEN) -> list[dict]:
    """Redovi kao iz tabele moves, za niz poteza.

    Svaki spec: san, before/after (cp iz ugla belog), opciono best (SAN najboljeg
    poteza, podrazumevano odigrani), second ((SAN, cp) drugog najboljeg) i pv.
    """
    board = chess.Board(start_fen)
    rows = []
    for ply, spec in enumerate(specs, start=1):
        move = board.parse_san(spec["san"])
        best = board.parse_san(spec.get("best", spec["san"]))
        second = spec.get("second")
        rows.append({
            "ply": ply,
            "color": "white" if board.turn == chess.WHITE else "black",
            "fen_before": board.fen(),
            "move_uci": move.uci(),
            "best_move_uci": best.uci(),
            "eval_before_cp": spec["before"], "eval_before_mate": None,
            "eval_after_cp": spec["after"], "eval_after_mate": None,
            "second_best_uci": board.parse_san(second[0]).uci() if second else None,
            "second_eval_cp": second[1] if second else None, "second_eval_mate": None,
            "pv": spec.get("pv"),
        })
        board.push(move)
    return rows


def labels_for(specs, book=frozenset(), start_fen=chess.STARTING_FEN) -> list[str]:
    labels, _ = classify_moves(make_rows(specs, start_fen), set(book))
    return [labels[ply] for ply in sorted(labels)]


def epd_after(*sans: str) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.epd()


# ---------------------------------------------------------------- pragovi

def test_najbolji_potez():
    assert labels_for([{"san": "e4", "before": 30, "after": 30}]) == ["best"]


@pytest.mark.parametrize("after, expected", [
    (-10, "excellent"),   # pad win% < 2
    (-38, "good"),        # 2-5
    (-82, "inaccuracy"),  # 5-10
    (-168, "mistake"),    # 10-20
    (-400, "blunder"),    # >= 20
])
def test_oznaka_po_padu_win_procenta(after, expected):
    specs = [{"san": "a3", "best": "e4", "before": 0, "after": after}]
    assert labels_for(specs) == [expected]


# ---------------------------------------------------------------- Book

def test_book_dok_partija_ide_kroz_teoriju_i_ne_vraca_se_posle_izlaska():
    book = {epd_after("e4"), epd_after("e4", "e5", "Nf3")}  # pozicija posle 1...e5 nije u knjizi
    specs = [
        {"san": "e4", "before": 30, "after": 30},
        {"san": "e5", "before": 30, "after": 30},
        {"san": "Nf3", "before": 30, "after": 30},
    ]
    assert labels_for(specs, book) == ["book", "best", "best"]


# ---------------------------------------------------------------- Miss

def blunder_then(white_reply_after: int) -> list[dict]:
    """1.e4, 1...f6?? (crni gubi ~28 poena win%), pa beli igra 2.a3 umesto 2.Qh5+."""
    return [
        {"san": "e4", "before": 30, "after": 30},
        {"san": "f6", "best": "e5", "before": 30, "after": 400},
        {"san": "a3", "best": "Qh5+", "before": 400, "after": white_reply_after},
    ]


def test_miss_kad_se_propusti_prilika_posle_protivnikove_greske():
    assert labels_for(blunder_then(30))[2] == "miss"


def test_nije_miss_kad_igrac_padne_ispod_pozicije_pre_greske():
    assert labels_for(blunder_then(-300))[2] == "blunder"


# ---------------------------------------------------------------- Great

def test_great_kad_je_drugi_najbolji_potez_gruba_greska():
    specs = [{"san": "e4", "before": 30, "after": 30, "second": ("d4", -400)}]
    assert labels_for(specs) == ["great"]


def test_nije_great_kad_postoji_dobra_alternativa():
    specs = [{"san": "e4", "before": 30, "after": 30, "second": ("d4", 20)}]
    assert labels_for(specs) == ["best"]


def test_uzimanje_posle_protivnikove_greske_nije_great():
    specs = [
        {"san": "e4", "before": 30, "after": 30},
        {"san": "d5", "best": "e5", "before": 30, "after": 400},
        {"san": "exd5", "before": 400, "after": 400, "second": ("Nc3", -50)},
    ]
    assert labels_for(specs)[2] == "best"


# ---------------------------------------------------------------- žrtve i Brilliant

ITALIAN = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQ - 0 1"


def test_is_sacrifice():
    board = chess.Board(ITALIAN)
    assert is_sacrifice(board, board.parse_san("Bxf7+"))      # lovac za pešaka
    assert not is_sacrifice(board, board.parse_san("d3"))     # miran potez


def test_zrtva_se_potvrdjuje_na_kraju_razmene():
    board = chess.Board(ITALIAN)
    move = board.parse_san("Nxe5")
    # 1.Nxe5 Nxe5 2.Bb3 d6: beli ostaje bez figure za pešaka - žrtva je potvrđena
    assert sacrifice_confirmed(board, move, ["Nxe5", "Bb3", "d6"])
    # 1.Nxe5 Nxe5 2.d4 Bxd4 3.Qxd4: vilicom beli vraća figuru u nastavku razmene - nije žrtva
    assert not sacrifice_confirmed(board, move, ["Nxe5", "d4", "Bxd4", "Qxd4"])


# Prava pozicija iz partije: 30...Rg7 ostavlja lovca na a5 zarad napada po g-liniji
RG7_FEN = "2b3k1/r7/p1N1pq2/b1Pp1p1p/Pp1P1P2/1P2P3/2B3P1/R4RK1 b - - 0 30"


def test_brilliant_zrtva_figure_koja_ostavlja_dobru_poziciju():
    specs = [{"san": "Rg7", "before": -265, "after": -255,
              "second": ("Qg7", -145), "pv": "Rg7 Nxa5 h4 Rae1 h3 Re2"}]
    assert labels_for(specs, start_fen=RG7_FEN) == ["brilliant"]


def test_nije_brilliant_u_vec_dobijenoj_poziciji():
    specs = [{"san": "Rg7", "before": -900, "after": -900, "pv": "Rg7 Nxa5 h4 Rae1 h3 Re2"}]
    assert labels_for(specs, start_fen=RG7_FEN) == ["best"]
