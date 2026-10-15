"""Knjiga otvaranja iz TSV fajlova i keš na disku."""

import chess

from app.analysis import openings


def test_load_book_sadrzi_sve_medjupozicije_i_pravi_kes(tmp_path):
    (tmp_path / "a.tsv").write_text("eco\tname\tpgn\nC20\tKing's Pawn Game\t1. e4 e5 2. Nf3\n",
                                    encoding="utf-8")
    book = openings.load_book(tmp_path)

    board = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
        assert board.epd() in book
    assert len(book) == 3
    assert (tmp_path / openings.BOOK_CACHE_NAME).exists()


def test_load_book_cita_kes_kad_je_noviji_od_tsv(tmp_path):
    (tmp_path / "a.tsv").write_text("eco\tname\tpgn\nB00\tTest\t1. e4\n", encoding="utf-8")
    openings.load_book(tmp_path)
    openings._book_cache.clear()

    # Keš sa izmišljenom pozicijom: ako se učita keš, a ne TSV, ona je u knjizi
    (tmp_path / openings.BOOK_CACHE_NAME).write_text("izmisljena-pozicija", encoding="utf-8")
    assert openings.load_book(tmp_path) == {"izmisljena-pozicija"}
