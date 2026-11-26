"""Route board authoring and deterministic simulation, shared by Go, hints and scoring."""
import json
import random
from collections import deque
from functools import lru_cache
from itertools import product
from pathlib import Path

from . import workshop

PUZZLES = json.loads((Path(__file__).resolve().parents[1] / "content/route_puzzles.json").read_text())
PUZZLES.update(workshop.GAMES)
# Clockwise quarter turns from north. Mutable pieces carry a small local state.
TILES = {
    ".": ("grass", 0), "S": ("source", 1), "G": ("goal", 0),
    "-": ("line", 0), "|": ("line", 1), "i": ("turnLine", 1),
    "c": ("turnBend", 1), "b": ("bend", 0), "e": ("bend", 1),
    "q": ("bend", 3), "V": ("valve", 0), "v": ("openValve", 1),
    "T": ("tee", 0), "J": ("switch", 0), "P": ("passenger", 0),
    "o": ("socket", 0),
}
STATES = {"turnLine": 2, "turnBend": 4, "valve": 2, "openValve": 2, "switch": 2, "socket": 5}
OFFSETS = ((0, -1), (1, 0), (0, 1), (-1, 0))


# Alternate footprints keep each stage's goal and introduce different turns
# and positions for the child's decisions.
ALTERNATE_MAPS = {
    "water": [
        ["..G.", "..|.", "SVq."], ["....", "S-c.", "..|.", "..G."],
        ["....", "So..", ".|..", ".G.."], ["......", "S--TVG", "...|..", "...v.."],
        ["......", "S-TV-G", "..|...", "..c--G"],
    ],
    "train": [
        ["..G.", "..|.", "Siq."], ["....", "S-o.", "..|.", "..G."],
        [".....", "SJ---", ".|...", ".b--G"],
        ["......", "SJ---G", ".|...|", ".c-P-q"],
        ["......", "S-J---", "..|...", "..cPJG", "....G."],
    ],
}


def stretch_route(grid, rng):
    """Insert a column of connecting rail/pipe wherever the old route crossed the cut."""
    cut = rng.randrange(1, len(grid[0]))
    for row in grid:
        crossing = row[cut - 1][0] != "grass" and row[cut][0] != "grass"
        row.insert(cut, ("line", 0) if crossing else ("grass", 0))


def layout(key, index, seed):
    spec = PUZZLES[key]
    rows = spec["levels"][index][2]
    rotation = seed % 4
    if seed >= 4:
        rng = random.Random(f"{key}/{seed}/{index}")
        if rng.randrange(2):
            rows = ALTERNATE_MAPS[spec["mode"]][index]
    grid = [[TILES[token] for token in row] for row in rows]
    if seed >= 4:
        stretch_route(grid, rng)
        if rng.randrange(2) and len(grid[0]) < 7:
            stretch_route(grid, rng)
        grid = [[(kind, (angle + 1) % 4) for kind, angle in row] for row in zip(*reversed(grid), strict=True)]
        if rng.randrange(2):
            stretch_route(grid, rng)
        rotation = rng.randrange(4)
    for _ in range(rotation):
        grid = list(zip(*reversed(grid), strict=True))
    return tuple(tuple((kind, (angle + rotation) % 4) for kind, angle in row) for row in grid)


@lru_cache(maxsize=None)
def round_layouts(key, index):
    layouts = []
    seen = set()
    for seed in range(2048):
        board = layout(key, index, seed)
        # Ignore decorative orientation when deciding whether a board is new.
        signature = tuple(tuple((kind, 0 if kind in {"grass", "goal"} else
                          angle % 2 if kind in {"line", "valve", "openValve", "passenger", "turnLine"} else angle)
                          for kind, angle in row) for row in board)
        if signature not in seen:
            layouts.append(board)
            seen.add(signature)
            if len(layouts) == 40:
                return tuple(layouts)
    raise ValueError(f"Insufficient different layouts for {key} stage {index + 1}")


def route_lesson(key, turns=0):
    if key in workshop.GAMES:
        return workshop.lesson(key, turns)
    spec = PUZZLES[key]
    items = []
    for index, (name, prompt, _) in enumerate(spec["levels"]):
        grid = round_layouts(key, index)[turns]
        cells = [dict(kind=kind, angle=angle, states=STATES.get(kind, 1)) for row in grid for kind, angle in row]
        board = dict(mode=spec["mode"], name=name, width=len(grid[0]), cells=cells)
        items.append(dict(prompt=prompt, board=board, answer="", choices=[], level=(1, 1, 2, 3, 3)[index]))
    return dict(title=spec["title"], skill=spec["skill"], kind="puzzle", age="4–8", items=items,
                category="Logic puzzles", participation="Independent", strand="Causal reasoning", level=2)


def parse_moves(board, submitted):
    limits = [cell["states"] for cell in board["cells"] if cell["states"] > 1]
    if len(submitted) != len(limits) or any(c not in "01234" for c in submitted):
        return None
    moves = tuple(map(int, submitted))
    return moves if all(m < limit for m, limit in zip(moves, limits)) else None


def connections(cell, state):
    kind, angle = cell["kind"], cell["angle"]
    if kind == "source":
        return [angle]
    if kind == "goal":
        return list(range(4))
    if kind == "grass" or (kind == "socket" and state == 0):
        return []
    if kind in ("turnLine", "turnBend"):
        angle += state
    if kind == "socket":
        angle += state - 1
    ports = (1, 3)
    if kind in ("bend", "turnBend", "socket"):
        ports = (0, 1)
    elif kind == "tee":
        ports = (3, 1, 2)
    elif kind == "switch":
        ports = (3, 2 if state else 1)
    return [(p + angle) % 4 for p in ports]


def simulate(board, moves):
    if board["mode"] not in {"water","train"}:
        return workshop.simulate(board, moves)
    cells, width = board["cells"], board["width"]
    changes = iter(moves)
    states = [next(changes) if cell["states"] > 1 else 0 for cell in cells]
    source = next(i for i, cell in enumerate(cells) if cell["kind"] == "source")
    queue = deque([(source, None)])
    trace, seen, goals, passengers = [], set(), set(), set()
    fault = None
    closed_valves = []
    while queue:
        pos, incoming = queue.popleft()
        if (pos, incoming) in seen:
            if board["mode"] == "train" and not fault:
                fault = ("loop", pos)
            continue
        seen.add((pos, incoming))
        cell = cells[pos]
        kind = cell["kind"]
        ports = connections(cell, states[pos])
        if incoming is not None and (incoming not in ports or kind == "source"):
            if not fault:
                fault = ("gap", pos)
            continue
        trace.append(pos)
        if kind == "goal":
            goals.add(pos)
            continue
        if kind == "passenger":
            passengers.add(pos)
        if (kind == "valve" and states[pos] == 0) or (kind == "openValve" and states[pos] == 1):
            closed_valves.append(pos)
            continue
        for direction in ports:
            if direction == incoming:
                continue
            dx, dy = OFFSETS[direction]
            x, y = pos % width + dx, pos // width + dy
            if 0 <= x < width and 0 <= y < len(cells) // width:
                queue.append((y * width + x, (direction + 2) % 4))
            elif not fault:
                fault = ("gap", pos)
    if not fault:
        for kind, reached in (("passenger", passengers), ("goal", goals)):
            targets = {i for i, cell in enumerate(cells) if cell["kind"] == kind}
            if kind == "goal" and board["mode"] == "train" and goals:
                continue
            if targets - reached:
                fault = ("closed", closed_valves[0]) if kind == "goal" and closed_valves else (kind, min(targets - reached))
                break
    return {"trace": trace, "success": fault is None, "reason": fault[0] if fault else "",
            "spot": fault[1] if fault else trace[-1]}


def hint(board, moves):
    """Highlight a decision leading to a nearest valid route, including alternate routes."""
    pieces = [(i, cell["states"]) for i, cell in enumerate(board["cells"]) if cell["states"] > 1]
    solutions = (s for s in product(*(range(limit) for _, limit in pieces)) if simulate(board, s)["success"])
    target = min(solutions, key=lambda s: sum(a != b for a, b in zip(moves, s)))
    return next((i for (i, _), a, b in zip(pieces, moves, target) if a != b), None)
