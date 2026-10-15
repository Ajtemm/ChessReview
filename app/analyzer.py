"""Analiza partija Stockfish-om: ocene, najbolji potez, varijanta i oznake poteza."""

import argparse
import csv
import io
import math
import sqlite3
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from app import db
from app.config import load_config, resolve_path

# Statusi partija koje treba (ponovo) analizirati
TO_ANALYZE = ("pending", "error")


def open_engine(config: dict) -> chess.engine.SimpleEngine:
    """Pokreće Stockfish sa putanje iz config.json."""
    return chess.engine.SimpleEngine.popen_uci(config["stockfish_path"])


def _score_fields(score: chess.engine.Score) -> tuple[int | None, int | None]:
    """Vraća (centipešaci, mat) iz ugla belog; jedno od dva je uvek None."""
    mate = score.mate()
    if mate is not None:
        return None, mate
    return score.score(), None


def _evaluate(
    engine: chess.engine.SimpleEngine, board: chess.Board, depth: int
) -> dict:
    """Ocena jedne pozicije, najbolji i drugi najbolji potez i glavna varijanta."""
    empty = {"best_uci": None, "best_san": None, "pv": None,
             "second_uci": None, "second_cp": None, "second_mate": None}
    # Završne pozicije ocenjujemo bez engine-a
    if board.is_checkmate():
        # Mat 0: mat je na tabli, pobedio je onaj ko je odigrao poslednji potez
        return {**empty, "cp": None, "mate": 0}
    if board.is_stalemate() or board.is_insufficient_material():
        return {**empty, "cp": 0, "mate": None}

    # MultiPV 2: drugi najbolji potez treba za oznaku Great (jedini dobar potez)
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
    info = infos[0]
    cp, mate = _score_fields(info["score"].white())

    second = {"second_uci": None, "second_cp": None, "second_mate": None}
    if len(infos) > 1 and infos[1].get("pv"):
        second_cp, second_mate = _score_fields(infos[1]["score"].white())
        second = {"second_uci": infos[1]["pv"][0].uci(),
                  "second_cp": second_cp, "second_mate": second_mate}

    pv_moves = info.get("pv") or []
    pv_san = []
    tmp = board.copy(stack=False)
    for move in pv_moves:
        pv_san.append(tmp.san(move))
        tmp.push(move)

    best = pv_moves[0] if pv_moves else None
    return {
        "cp": cp,
        "mate": mate,
        "best_uci": best.uci() if best else None,
        "best_san": pv_san[0] if pv_san else None,
        "pv": " ".join(pv_san) or None,
        **second,
    }


def analyze_moves(pgn: str, engine: chess.engine.SimpleEngine, depth: int) -> list[dict]:
    """Prolazi kroz sve poteze partije i vraća redove za tabelu moves."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("PGN nije moguće pročitati")

    board = game.board()
    # Ocena posle poteza N je ocena pre poteza N+1, pa svaku poziciju analiziramo jednom
    current = _evaluate(engine, board, depth)

    rows = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        row = {
            "ply": ply,
            "move_number": board.fullmove_number,
            "color": "white" if board.turn == chess.WHITE else "black",
            "fen_before": board.fen(),
            "move_san": board.san(move),
            "move_uci": move.uci(),
            "eval_before_cp": current["cp"],
            "eval_before_mate": current["mate"],
            "best_move_san": current["best_san"],
            "best_move_uci": current["best_uci"],
            "pv": current["pv"],
            "second_best_uci": current["second_uci"],
            "second_eval_cp": current["second_cp"],
            "second_eval_mate": current["second_mate"],
        }
        board.push(move)
        current = _evaluate(engine, board, depth)
        row["eval_after_cp"] = current["cp"]
        row["eval_after_mate"] = current["mate"]
        rows.append(row)
    return rows


# ---------------------------------------------------------------- win% i tačnost

# Lichess: ocene se seku na ±1000 cp, mat se računa kao ±1000
CP_CEILING = 1000


def _white_cp(cp: int | None, mate: int | None, mover: str) -> int:
    """Ocena iz ugla belog u cp; `mover` je ko je odigrao potez (za mat na tabli)."""
    if mate is not None:
        if mate == 0:
            return CP_CEILING if mover == "white" else -CP_CEILING
        return CP_CEILING if mate > 0 else -CP_CEILING
    return max(-CP_CEILING, min(CP_CEILING, cp or 0))


def win_percent(cp: int) -> float:
    """Lichess formula: šansa za pobedu (0-100) za datu ocenu u cp."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Lichess: tačnost jednog poteza iz pada win% (oba iz ugla igrača na potezu)."""
    if win_after >= win_before:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * (win_before - win_after)) - 3.166924740191411
    # +1 je Lichess "bonus za nesigurnost"
    return max(0.0, min(100.0, raw + 1))


def _std_dev(xs: list[float]) -> float:
    mean = sum(xs) / len(xs)
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def game_accuracy(white_wins: list[float]) -> dict[str, float | None]:
    """Lichess tačnost partije za oba igrača.

    `white_wins` je win% iz ugla belog za početnu poziciju i posle svakog polupoteza.
    Svaki potez se meri težinom = volatilnost pozicije (std. devijacija u prozoru),
    a rezultat je prosek težinske i harmonijske sredine tačnosti poteza.
    """
    n_moves = len(white_wins) - 1
    if n_moves < 1:
        return {"white": None, "black": None}

    window = max(2, min(8, n_moves // 10))
    windows = [white_wins[:window]] * (min(window, len(white_wins)) - 2)
    windows += [white_wins[i:i + window] for i in range(max(1, len(white_wins) - window + 1))]
    weights = [max(0.5, min(12.0, _std_dev(w))) for w in windows]

    per_color: dict[str, list[tuple[float, float]]] = {"white": [], "black": []}
    for i in range(n_moves):
        prev, nxt = white_wins[i], white_wins[i + 1]
        if i % 2 == 0:
            acc, color = move_accuracy(prev, nxt), "white"
        else:
            acc, color = move_accuracy(100 - prev, 100 - nxt), "black"
        per_color[color].append((acc, weights[i]))

    result: dict[str, float | None] = {}
    for color, items in per_color.items():
        if not items:
            result[color] = None
            continue
        weighted = sum(a * w for a, w in items) / sum(w for _, w in items)
        harmonic = len(items) / sum(1 / max(1.0, a) for a, _ in items)
        result[color] = (weighted + harmonic) / 2
    return result


# ---------------------------------------------------------------- Book

_book_cache: dict[Path, set[str]] = {}

# Gotov skup pozicija na disku: pravljenje iz TSV-a traje ~3 s i drži GIL,
# pa bi usporilo server dok se analiza vrti u pozadini
BOOK_CACHE_NAME = "book_cache.epd"


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
    """Skup pozicija (EPD) iz lichess chess-openings TSV fajlova, uključujući međupozicije."""
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


# ---------------------------------------------------------------- oznake poteza

# Pad win% (u procentnim poenima) u odnosu na najbolji potez: gornje granice oznaka
THRESHOLDS = (
    (2.0, "excellent"),
    (5.0, "good"),
    (10.0, "inaccuracy"),
    (20.0, "mistake"),
)

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

# Brilliant: koliko materijala (neto) mora da se ponudi i u kakvoj poziciji
SACRIFICE_MIN = 2
SACRIFICE_MAX_PLIES = 12            # najviše polupoteza varijante koje pratimo u razmeni
BRILLIANT_MIN_WIN_AFTER = 50.0      # pozicija posle i dalje dobra za igrača
BRILLIANT_MAX_WIN_BEFORE = 90.0     # a nije bila već potpuno dobijena
# Great: drugi najbolji potez bi bio bar ovoliko lošiji (tj. Blunder)
GREAT_MIN_SECOND_DROP = 20.0
# Great samo dok partija nije odlučena (win% igrača pre poteza)
GREAT_WIN_RANGE = (10.0, 90.0)


def _label_by_drop(drop: float) -> str:
    for limit, label in THRESHOLDS:
        if drop < limit:
            return label
    return "blunder"


def is_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    """Da li potez ostavlja figuru (ne pešaka) koju protivnik može da uzme uz dobitak materijala.

    Jednostavna procena bez razmene u više koraka: figura "visi" ako je napada
    slabija figura ili ako nije branjena. Uzima se u obzir i ono što je potez uzeo.
    """
    if board.is_en_passant(move):
        captured = PIECE_VALUES[chess.PAWN]
    else:
        victim = board.piece_at(move.to_square)
        captured = PIECE_VALUES[victim.piece_type] if victim else 0

    after = board.copy(stack=False)
    after.push(move)
    mover = board.turn
    offered = 0
    for reply in after.legal_moves:
        target = after.piece_at(reply.to_square)
        if target is None or target.color != mover or target.piece_type in (chess.PAWN, chess.KING):
            continue
        value = PIECE_VALUES[target.piece_type]
        attacker = PIECE_VALUES[after.piece_at(reply.from_square).piece_type]
        if not after.is_attacked_by(mover, reply.to_square):
            offered = max(offered, value)
        elif attacker < value:
            offered = max(offered, value - attacker)
    return offered - captured >= SACRIFICE_MIN


def _material_balance(board: chess.Board, color: chess.Color) -> int:
    """Materijal igrača `color` minus materijal protivnika (bez kraljeva)."""
    balance = 0
    for piece in board.piece_map().values():
        if piece.piece_type != chess.KING:
            value = PIECE_VALUES[piece.piece_type]
            balance += value if piece.color == color else -value
    return balance


def sacrifice_confirmed(board: chess.Board, move: chess.Move, line_after: list[str]) -> bool:
    """Žrtva potvrđena varijantom: kad se razmena u varijanti završi, igrač je i dalje
    u minusu bar SACRIFICE_MIN materijala (figura se ne vraća).

    Pratimo bar protivnikov odgovor i sledeći potez igrača, pa dalje dok god
    varijanta nastavlja uzimanjima. `line_after` su potezi (SAN) iz pozicije posle poteza.
    """
    if len(line_after) < 2:
        return False
    mover = board.turn
    start = _material_balance(board, mover)
    tmp = board.copy(stack=False)
    tmp.push(move)
    for k, san in enumerate(line_after[:SACRIFICE_MAX_PLIES]):
        next_move = tmp.parse_san(san)
        if k >= 2 and not tmp.is_capture(next_move):
            break
        tmp.push(next_move)
    return _material_balance(tmp, mover) <= start - SACRIFICE_MIN


def classify_moves(moves: list, book: set[str]) -> tuple[dict[int, str], dict[str, float | None]]:
    """Oznake za sve poteze partije i tačnost oba igrača.

    `moves` su redovi iz tabele moves (poređani po ply). Vraća ({ply: oznaka}, tačnost).
    """
    labels: dict[int, str] = {}
    in_book = True
    prev_capture_square = None
    white_wins: list[float] = []

    for i, m in enumerate(moves):
        color = m["color"]
        sign = 1 if color == "white" else -1
        board = chess.Board(m["fen_before"])
        move = chess.Move.from_uci(m["move_uci"])

        # Ocena pre poteza = ocena najboljeg poteza; win% iz ugla igrača na potezu
        cp_before = _white_cp(m["eval_before_cp"], m["eval_before_mate"], color)
        cp_after = _white_cp(m["eval_after_cp"], m["eval_after_mate"], color)
        win_before = win_percent(sign * cp_before)
        win_after = win_percent(sign * cp_after)
        drop = win_before - win_after
        if not white_wins:
            white_wins.append(win_percent(cp_before))
        white_wins.append(win_percent(cp_after))

        is_best = m["move_uci"] == m["best_move_uci"]
        is_capture = board.is_capture(move)

        board_after = board.copy(stack=False)
        board_after.push(move)
        if in_book and board_after.epd() in book:
            label = "book"
        else:
            # Kad se jednom izađe iz teorije, ne vraćamo se u nju
            in_book = False
            label = "best" if is_best else _label_by_drop(drop)
            # Varijanta iz pozicije posle poteza: iz analize sledećeg polupoteza, a za
            # poslednji potez partije iz varijante samog poteza (ako je odigran najbolji)
            if i + 1 < len(moves) and moves[i + 1]["pv"]:
                line_after = moves[i + 1]["pv"].split()
            elif is_best and m["pv"]:
                line_after = m["pv"].split()[1:]
            else:
                line_after = []

            if label in ("best", "excellent") and (
                win_after >= BRILLIANT_MIN_WIN_AFTER
                and win_before < BRILLIANT_MAX_WIN_BEFORE
                and is_sacrifice(board, move)
                and sacrifice_confirmed(board, move, line_after)
            ):
                label = "brilliant"
            elif is_best and m["second_best_uci"] is not None:
                cp_second = _white_cp(m["second_eval_cp"], m["second_eval_mate"], color)
                second_drop = win_before - win_percent(sign * cp_second)
                # Očigledni potezi nisu Great: uzimanje nazad na istom polju,
                # uzimanje posle protivnikove greške (kažnjavanje) i mat u 1
                recapture = is_capture and move.to_square == prev_capture_square
                punishes = is_capture and labels.get(m["ply"] - 1) in ("mistake", "blunder")
                if (
                    second_drop >= GREAT_MIN_SECOND_DROP
                    and GREAT_WIN_RANGE[0] <= win_before <= GREAT_WIN_RANGE[1]
                    and not recapture
                    and not punishes
                    and not board_after.is_checkmate()
                ):
                    label = "great"

        labels[m["ply"]] = label
        prev_capture_square = move.to_square if is_capture else None

    return labels, game_accuracy(white_wins)


def classify_game(conn: sqlite3.Connection, url: str, config: dict | None = None) -> Counter:
    """Računa i čuva oznake poteza i tačnost za već analiziranu partiju (bez Stockfish-a)."""
    config = config or load_config()
    book = load_book(resolve_path(config["openings_dir"]))
    labels, accuracy = classify_moves(db.get_moves(conn, url), book)
    with conn:
        db.save_classifications(conn, url, labels)
        db.set_accuracy(conn, url, accuracy["white"], accuracy["black"])
    return Counter(labels.values())


def classify_all() -> int:
    """Ponovo računa oznake za sve analizirane partije. Vraća broj partija."""
    config = load_config()
    conn = db.connect()
    try:
        games = db.list_games_by_status(conn, ("done",))
        for game in games:
            classify_game(conn, game["url"], config)
        return len(games)
    finally:
        conn.close()


# ---------------------------------------------------------------- analiza

def analyze_game(
    conn: sqlite3.Connection,
    url: str,
    engine: chess.engine.SimpleEngine | None = None,
    config: dict | None = None,
) -> int:
    """Analizira jednu partiju iz baze i čuva rezultate. Vraća broj polupoteza."""
    config = config or load_config()
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")

    with conn:
        db.set_status(conn, url, "running")

    own_engine = engine is None
    if own_engine:
        engine = open_engine(config)
    try:
        rows = analyze_moves(game["pgn"], engine, int(config["analysis_depth"]))
        with conn:
            db.save_moves(conn, url, rows)
        classify_game(conn, url, config)
        with conn:
            db.set_status(conn, url, "done")
        return len(rows)
    except KeyboardInterrupt:
        # Prekinuto ručno: vraćamo partiju u red za analizu
        with conn:
            db.set_status(conn, url, "pending")
        raise
    except Exception:
        with conn:
            db.set_status(conn, url, "error")
        raise
    finally:
        if own_engine:
            engine.quit()


def analyze_pending(
    statuses: tuple[str, ...] = TO_ANALYZE,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict:
    """Analizira sve partije sa datim statusom. Vraća statistiku.

    `should_stop` se proverava između partija (za gašenje servera).
    """
    config = load_config()
    conn = db.connect()
    stats = {"done": 0, "error": 0}
    games = db.list_games_by_status(conn, statuses)
    if not games:
        conn.close()
        return stats

    engine = open_engine(config)
    try:
        for i, game in enumerate(games, start=1):
            if should_stop():
                break
            label = f"[{i}/{len(games)}] {game['white']} - {game['black']} ({game['end_time'][:10]})"
            try:
                plies = analyze_game(conn, game["url"], engine=engine, config=config)
                stats["done"] += 1
                print(f"{label}: {plies} polupoteza")
            except Exception as e:
                stats["error"] += 1
                print(f"{label}: GREŠKA {e}")
    finally:
        engine.quit()
        conn.close()
    return stats


# ---------------------------------------------------------------- ispis

def format_eval(cp: int | None, mate: int | None) -> str:
    """Ocena za prikaz: +0.35, #3, #-2, ili # kad je mat na tabli."""
    if mate is not None:
        return "#" if mate == 0 else f"#{mate}"
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


def print_moves(conn: sqlite3.Connection, url: str, pv_len: int = 5) -> None:
    """Ispisuje tabelu poteza sa ocenama i oznakama za jednu partiju."""
    game = db.get_game(conn, url)
    if game is None:
        raise KeyError(f"Partija nije u bazi: {url}")
    print(f"{game['white']} - {game['black']}  {game['result']}  ({game['time_control']}, {game['end_time'][:10]})")
    if game["white_accuracy"] is not None:
        print(f"Tačnost: beli {game['white_accuracy']:.1f}, crni {game['black_accuracy']:.1f}")
    print(f"{'Potez':>7}  {'SAN':<8} {'Pre':>7} {'Posle':>7}  {'Oznaka':<11} {'Najbolji':<8} Varijanta")
    for m in db.get_moves(conn, url):
        num = f"{m['move_number']}." if m["color"] == "white" else f"{m['move_number']}..."
        pv = " ".join((m["pv"] or "").split()[:pv_len])
        print(
            f"{num:>7}  {m['move_san']:<8} "
            f"{format_eval(m['eval_before_cp'], m['eval_before_mate']):>7} "
            f"{format_eval(m['eval_after_cp'], m['eval_after_mate']):>7}  "
            f"{m['classification'] or '-':<11} {m['best_move_san'] or '-':<8} {pv}"
        )


LABEL_ORDER = ("brilliant", "great", "best", "excellent", "good", "book",
               "inaccuracy", "mistake", "blunder")


def print_stats() -> None:
    """Broj poteza po oznakama za sve analizirane partije: moji, protivnikovi, ukupno."""
    conn = db.connect()
    try:
        rows = conn.execute(
            """SELECT m.classification AS label, m.color = g.my_color AS mine, COUNT(*) AS n
               FROM moves m JOIN games g ON g.url = m.game_url
               WHERE g.analysis_status = 'done'
               GROUP BY 1, 2"""
        ).fetchall()
        counts = {(r["label"], bool(r["mine"])): r["n"] for r in rows}
        n_games = conn.execute(
            "SELECT COUNT(*) FROM games WHERE analysis_status = 'done'"
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"Analiziranih partija: {n_games}")
    print(f"{'Oznaka':<11} {'Ja':>5} {'Protivnik':>10} {'Ukupno':>7}")
    for label in LABEL_ORDER:
        mine, theirs = counts.get((label, True), 0), counts.get((label, False), 0)
        print(f"{label:<11} {mine:>5} {theirs:>10} {mine + theirs:>7}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stockfish analiza partija iz baze")
    parser.add_argument("--game", metavar="URL", help="analiziraj samo ovu partiju")
    parser.add_argument("--show", metavar="URL", help="prikaži tabelu poteza za partiju")
    parser.add_argument("--classify", action="store_true",
                        help="ponovo izračunaj oznake i tačnost za analizirane partije")
    parser.add_argument("--stats", action="store_true", help="broj poteza po oznakama")
    args = parser.parse_args()

    if args.classify:
        print(f"Oznake izračunate za {classify_all()} partija")
    elif args.stats:
        print_stats()
    elif args.game:
        conn = db.connect()
        try:
            plies = analyze_game(conn, args.game)
            print(f"Analizirano {plies} polupoteza")
        finally:
            conn.close()
    elif args.show:
        conn = db.connect()
        try:
            print_moves(conn, args.show)
        finally:
            conn.close()
    else:
        stats = analyze_pending()
        print(f"Analizirano: {stats['done']}, grešaka: {stats['error']}")


if __name__ == "__main__":
    main()
