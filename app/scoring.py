"""Win% i tačnost po Lichess formulama."""

import math

# Lichess: ocene se seku na ±1000 cp, mat se računa kao ±1000
CP_CEILING = 1000


def white_cp(cp: int | None, mate: int | None, mover: str) -> int:
    """Ocena iz baze kao cp iz ugla belog (sečena na ±CP_CEILING).

    `mover` je ko je odigrao poslednji potez; treba samo za mat na tabli (mate = 0).
    """
    if mate is not None:
        if mate == 0:
            return CP_CEILING if mover == "white" else -CP_CEILING
        return CP_CEILING if mate > 0 else -CP_CEILING
    return max(-CP_CEILING, min(CP_CEILING, cp or 0))


def win_percent(cp: int) -> float:
    """Lichess formula: šansa za pobedu (0-100) za datu ocenu u cp."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def white_win_percent(cp: int | None, mate: int | None, mover: str) -> float:
    """Win% iz ugla belog za ocenu iz baze; `mover` je ko je odigrao poslednji potez."""
    return win_percent(white_cp(cp, mate, mover))


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


def _volatility_weights(white_wins: list[float]) -> list[float]:
    """Težina svakog poteza = std. devijacija win% u kliznom prozoru (Lichess)."""
    n_moves = len(white_wins) - 1
    window = max(2, min(8, n_moves // 10))
    # Prvi potezi dobijaju težinu prvog punog prozora
    windows = [white_wins[:window]] * (min(window, len(white_wins)) - 2)
    windows += [white_wins[i:i + window] for i in range(max(1, len(white_wins) - window + 1))]
    return [max(0.5, min(12.0, _std_dev(w))) for w in windows]


def game_accuracy(white_wins: list[float]) -> dict[str, float | None]:
    """Lichess tačnost partije za oba igrača.

    `white_wins` je win% iz ugla belog za početnu poziciju i posle svakog polupoteza.
    Rezultat je prosek težinske i harmonijske sredine tačnosti poteza.
    """
    n_moves = len(white_wins) - 1
    if n_moves < 1:
        return {"white": None, "black": None}

    weights = _volatility_weights(white_wins)
    per_color: dict[str, list[tuple[float, float]]] = {"white": [], "black": []}
    for i in range(n_moves):
        before, after = white_wins[i], white_wins[i + 1]
        if i % 2 == 0:
            per_color["white"].append((move_accuracy(before, after), weights[i]))
        else:
            per_color["black"].append((move_accuracy(100 - before, 100 - after), weights[i]))

    result: dict[str, float | None] = {}
    for color, items in per_color.items():
        if not items:
            result[color] = None
            continue
        weighted = sum(a * w for a, w in items) / sum(w for _, w in items)
        harmonic = len(items) / sum(1 / max(1.0, a) for a, _ in items)
        result[color] = (weighted + harmonic) / 2
    return result
