"""Oznake poteza (Brilliant ... Blunder, Book) i tačnost partije iz već sačuvane analize."""

from dataclasses import dataclass

import chess

from app.scoring import game_accuracy, white_cp, win_percent

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
# Protivnikove greške posle kojih uzimanje nije Great nego očigledno kažnjavanje
PUNISHABLE = ("mistake", "miss", "blunder")
# Miss: posle protivnikove greške potez bi bio Mistake/Blunder, ali igrač nije pao
# ispod pozicije koju je imao pre te greške (uz ovu toleranciju) - samo je propustio priliku
MISS_TOLERANCE = 5.0
# Greške posle kojih propušten potez postaje Miss. Bez "miss": kad protivnik propusti
# da kazni moju grešku, a ja je ponovim, to je moja nova greška, ne propuštena prilika
MISS_AFTER = ("mistake", "blunder")


# ---------------------------------------------------------------- materijal i žrtve

def material_balance(board: chess.Board, color: chess.Color) -> int:
    """Materijal igrača `color` minus materijal protivnika (bez kraljeva)."""
    balance = 0
    for piece in board.piece_map().values():
        if piece.piece_type != chess.KING:
            value = PIECE_VALUES[piece.piece_type]
            balance += value if piece.color == color else -value
    return balance


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


def sacrifice_confirmed(board: chess.Board, move: chess.Move, line_after: list[str]) -> bool:
    """Žrtva potvrđena varijantom: kad se razmena u varijanti završi, igrač je i dalje
    u minusu bar SACRIFICE_MIN materijala (figura se ne vraća).

    Pratimo bar protivnikov odgovor i sledeći potez igrača, pa dalje dok god
    varijanta nastavlja uzimanjima. `line_after` su potezi (SAN) iz pozicije posle poteza.
    """
    if len(line_after) < 2:
        return False
    mover = board.turn
    start = material_balance(board, mover)
    tmp = board.copy(stack=False)
    tmp.push(move)
    for k, san in enumerate(line_after[:SACRIFICE_MAX_PLIES]):
        next_move = tmp.parse_san(san)
        if k >= 2 and not tmp.is_capture(next_move):
            break
        tmp.push(next_move)
    return material_balance(tmp, mover) <= start - SACRIFICE_MIN


# ---------------------------------------------------------------- jedan potez

@dataclass
class MoveContext:
    """Sve što pravila za oznake treba da znaju o jednom potezu.

    Svi win% su iz ugla igrača koji vuče potez. Ocena pre poteza je ocena
    najboljeg poteza, pa je `drop` gubitak u odnosu na najbolji potez.
    """

    ply: int
    board: chess.Board          # pozicija pre poteza
    board_after: chess.Board
    move: chess.Move
    win_before: float
    win_after: float
    second_win: float | None    # posle drugog najboljeg poteza (None ako ga nema)
    is_best: bool
    is_capture: bool
    line_after: list[str]       # varijanta (SAN) iz pozicije posle poteza

    @property
    def drop(self) -> float:
        return self.win_before - self.win_after


def _line_after(moves: list, i: int, is_best: bool) -> list[str]:
    """Varijanta iz pozicije posle poteza: iz analize sledećeg polupoteza, a za
    poslednji potez partije iz varijante samog poteza (ako je odigran najbolji)."""
    if i + 1 < len(moves) and moves[i + 1]["pv"]:
        return moves[i + 1]["pv"].split()
    if is_best and moves[i]["pv"]:
        return moves[i]["pv"].split()[1:]
    return []


def _move_context(moves: list, i: int) -> MoveContext:
    m = moves[i]
    color = m["color"]
    sign = 1 if color == "white" else -1

    def mover_win(cp, mate):
        return win_percent(sign * white_cp(cp, mate, color))

    board = chess.Board(m["fen_before"])
    move = chess.Move.from_uci(m["move_uci"])
    board_after = board.copy(stack=False)
    board_after.push(move)
    is_best = m["move_uci"] == m["best_move_uci"]
    has_second = m["second_best_uci"] is not None
    return MoveContext(
        ply=m["ply"],
        board=board,
        board_after=board_after,
        move=move,
        win_before=mover_win(m["eval_before_cp"], m["eval_before_mate"]),
        win_after=mover_win(m["eval_after_cp"], m["eval_after_mate"]),
        second_win=mover_win(m["second_eval_cp"], m["second_eval_mate"]) if has_second else None,
        is_best=is_best,
        is_capture=board.is_capture(move),
        line_after=_line_after(moves, i, is_best),
    )


def _label_by_drop(drop: float) -> str:
    for limit, label in THRESHOLDS:
        if drop < limit:
            return label
    return "blunder"


def _is_brilliant(ctx: MoveContext) -> bool:
    """Najbolji ili skoro najbolji potez koji žrtvuje figuru, a pozicija ostaje dobra."""
    return (
        ctx.win_after >= BRILLIANT_MIN_WIN_AFTER
        and ctx.win_before < BRILLIANT_MAX_WIN_BEFORE
        and is_sacrifice(ctx.board, ctx.move)
        and sacrifice_confirmed(ctx.board, ctx.move, ctx.line_after)
    )


def _is_great(ctx: MoveContext, prev_label: str | None, prev_capture_square: int | None) -> bool:
    """Jedini dobar potez: drugi najbolji bi bio Blunder, a partija još nije odlučena.

    Očigledni potezi nisu Great: uzimanje nazad na istom polju, uzimanje posle
    protivnikove greške (kažnjavanje) i mat u 1.
    """
    if not ctx.is_best or ctx.second_win is None:
        return False
    recapture = ctx.is_capture and ctx.move.to_square == prev_capture_square
    punishes = ctx.is_capture and prev_label in PUNISHABLE
    return (
        ctx.win_before - ctx.second_win >= GREAT_MIN_SECOND_DROP
        and GREAT_WIN_RANGE[0] <= ctx.win_before <= GREAT_WIN_RANGE[1]
        and not recapture
        and not punishes
        and not ctx.board_after.is_checkmate()
    )


def _is_miss(ctx: MoveContext, prev_label: str | None, prev_win_before: float) -> bool:
    """Propuštena prilika posle protivnikove greške, bez pada ispod pozicije pre te greške.

    `prev_win_before` je win% protivnika pre njegovog poteza (njegov ugao).
    """
    if prev_label not in MISS_AFTER:
        return False
    win_before_error = 100 - prev_win_before
    return ctx.win_after >= win_before_error - MISS_TOLERANCE


def _classify(ctx: MoveContext, prev_label: str | None,
              prev_capture_square: int | None, prev_win_before: float) -> str:
    """Oznaka za potez van teorije."""
    label = "best" if ctx.is_best else _label_by_drop(ctx.drop)
    if label in ("best", "excellent") and _is_brilliant(ctx):
        return "brilliant"
    if label == "best" and _is_great(ctx, prev_label, prev_capture_square):
        return "great"
    if label in ("mistake", "blunder") and _is_miss(ctx, prev_label, prev_win_before):
        return "miss"
    return label


# ---------------------------------------------------------------- cela partija

def classify_moves(moves: list, book: set[str]) -> tuple[dict[int, str], dict[str, float | None]]:
    """Oznake za sve poteze partije i tačnost oba igrača.

    `moves` su redovi iz tabele moves (poređani po ply), `book` skup pozicija iz
    knjige otvaranja. Vraća ({ply: oznaka}, {"white": tačnost, "black": tačnost}).
    """
    labels: dict[int, str] = {}
    in_book = True
    prev_label: str | None = None
    prev_capture_square: int | None = None
    prev_win_before = 50.0
    white_wins: list[float] = []

    for i, m in enumerate(moves):
        ctx = _move_context(moves, i)

        # Win% iz ugla belog za tačnost partije: početna pozicija, pa posle svakog poteza
        if not white_wins:
            white_wins.append(win_percent(white_cp(m["eval_before_cp"], m["eval_before_mate"], m["color"])))
        white_wins.append(win_percent(white_cp(m["eval_after_cp"], m["eval_after_mate"], m["color"])))

        # Book dok god partija ide kroz teoriju; kad se jednom izađe, ne vraćamo se
        in_book = in_book and ctx.board_after.epd() in book
        if in_book:
            label = "book"
        else:
            label = _classify(ctx, prev_label, prev_capture_square, prev_win_before)

        labels[ctx.ply] = label
        prev_label = label
        prev_capture_square = ctx.move.to_square if ctx.is_capture else None
        prev_win_before = ctx.win_before

    return labels, game_accuracy(white_wins)
