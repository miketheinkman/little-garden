"""Five tabletop mechanisms using the shared route player, hint search and scoring."""
from collections import deque
import json
from pathlib import Path

GAMES = json.loads((Path(__file__).resolve().parents[1] / "content/workshop_puzzles.json").read_text())
OFFSETS = ((0, -1), (1, 0), (0, 1), (-1, 0))
KINDS = {"S":"source", "G":"goal", "#":"rock", "~":"water", "b":"bridgePeg", "m":"mirror",
         "n":"mirrorMount", "L":"lantern", ":":"air", "p":"path", "P":"parcel", "a":"arrow",
         "O":"gear", "g":"gearPeg", "1":"leverA", "2":"leverB", "A":"gateA", "B":"gateB", "X":"gateBoth"}
STATES = {"mirror":2, "mirrorMount":3, "bridgePeg":5, "arrow":4, "gearPeg":2, "leverA":2, "leverB":2}


def layouts(key, index, variant):
    spec = GAMES[key]
    mode = spec["mode"]
    rows = spec["levels"][index][2]
    width, height = len(rows[0]), len(rows)
    assert all(len(row) == width for row in rows)
    rotation, reflected, approach = variant % 4, bool(variant // 4 % 2), variant // 8
    # Add a lead-in before the first decision. Stagger the scenery on opposite banks.
    grid = {}
    background = {"light":"air","bridge":"water","delivery":"rock","gears":"ground","gates":"rock"}[mode]
    track = {"light":"air","bridge":"island","delivery":"path","gears":"gear","gates":"path"}[mode]
    for y, row in enumerate(rows):
        for x, token in enumerate(row):
            kind = KINDS.get(token, "island" if mode == "bridge" else background)
            if token == "S":
                grid[0,y] = "source"
                for step in range(1, approach + 1):
                    grid[step,y] = track
            else:
                grid[x+approach,y] = kind
    width += approach
    # An asymmetric rim gives short and long runs a clear top and bottom after a turn.
    grid[0,height] = "rock"
    height += 1
    cells = [None] * (width * height)
    new_width = height if rotation % 2 else width
    for y in range(height):
        for x in range(width):
            kind = grid.get((x,y), background)
            col, row = width-1-x if reflected else x, y
            w, h = width, height
            for _ in range(rotation):
                col, row, w, h = h-1-row, col, h, w
            direction = 3 if reflected else 1
            angle = (direction + rotation) % 4
            if kind in {"mirror", "mirrorMount"}:
                # The first mirror initially reflects east toward the bottom bank.
                angle = (1 + rotation + int(reflected)) % 2
            cell = dict(kind=kind, angle=angle, states=STATES.get(kind, 1))
            if kind == "bridgePeg":
                cell["perpendicular"] = (2 + rotation) % 4
            if kind == "source" and mode == "gears":
                cell.update(states=2 if index >= 3 else 1, clockwise=approach % 2 == 0)
            cells[row * new_width + col] = cell
    board = dict(mode=mode, name=spec["levels"][index][0], width=new_width, cells=cells)
    if mode == "gears":
        source, goal = [next(i for i,c in enumerate(cells) if c["kind"] == k) for k in ("source","goal")]
        distance = abs(source % new_width - goal % new_width) + abs(source // new_width - goal // new_width)
        natural = cells[source]["clockwise"] != bool(distance % 2)
        board["clockwise"] = natural if index < 3 else not natural
    return board


def lesson(key, variant):
    spec = GAMES[key]
    items = [dict(prompt=level[1], board=layouts(key, i, variant), answer="", choices=[], level=(1,1,2,3,3)[i])
             for i,level in enumerate(spec["levels"])]
    return dict(title=spec["title"], skill=spec["skill"], kind="puzzle", age="4–8", items=items,
                category="Logic puzzles", participation="Independent", strand="Causal reasoning", level=2)


def neighbor(board, pos, direction):
    width = board["width"]
    dx, dy = OFFSETS[direction]
    x, y = pos % width + dx, pos // width + dy
    if 0 <= x < width and 0 <= y < len(board["cells"]) // width:
        return y * width + x
    return None


def result(trace, reason="", spot=None):
    return dict(trace=trace, success=not reason, reason=reason, spot=trace[-1] if spot is None else spot)


def travel(board, states, start):
    cells = board["cells"]
    light = board["mode"] == "light"
    pickup = "lantern" if light else "parcel"
    needed = {i for i,c in enumerate(cells) if c["kind"] == pickup}
    trace, seen = [start], set()
    pos, direction = start, cells[start]["angle"]
    while (pos, direction) not in seen:
        seen.add((pos, direction))
        nxt = neighbor(board, pos, direction)
        if nxt is None:
            return result(trace, "edge")
        pos = nxt
        trace.append(pos)
        cell, state = cells[pos], states[pos]
        kind = cell["kind"]
        if kind == "rock":
            return result(trace, "rock")
        if kind == "goal":
            return result(trace, "pickup", min(needed)) if needed else result(trace)
        needed.discard(pos)
        if kind == "arrow":
            direction = (cell["angle"] + state) % 4
        elif kind == "mirror" or (kind == "mirrorMount" and state):
            tilt = (cell["angle"] + state - int(kind == "mirrorMount")) % 2
            direction = 3-direction if tilt else direction ^ 1
    return result(trace, "loop")


def bridge_edges(board, states):
    cells = board["cells"]
    links = {}
    for pos, cell in enumerate(cells):
        state = states[pos]
        if cell["kind"] != "bridgePeg" or not state:
            continue
        direction = cell["angle"] if state <= 2 else cell["perpendicular"]
        bank = neighbor(board, pos, (direction+2) % 4)
        span = [pos]
        far = neighbor(board, pos, direction)
        if state in (2,4):
            if far is None or cells[far]["kind"] != "water":
                continue
            span.append(far)
            far = neighbor(board, far, direction)
        land = {"island","source","goal"}
        if bank is not None and far is not None and cells[bank]["kind"] in land and cells[far]["kind"] in land:
            links.setdefault(bank, []).append(span + [far])
            links.setdefault(far, []).append(span[::-1] + [bank])
    return links


def switches(board, states):
    return {c["kind"] for i,c in enumerate(board["cells"]) if c["kind"].startswith("lever") and states[i]}


def connected(board, states, start):
    cells, mode = board["cells"], board["mode"]
    goal = next(i for i,c in enumerate(cells) if c["kind"] == "goal")
    open_levers = switches(board, states)
    links = bridge_edges(board, states) if mode == "bridge" else {}
    allowed = {"source","goal","island","gear","path"}
    queue = deque([(start,[start])])
    reached, powered = {start}, []
    stop, blocked = [start], None
    while queue:
        pos, path = queue.popleft()
        powered.append(pos)
        if pos == goal and mode != "gears":
            return result(path)
        for span in links.get(pos, []):
            if span[-1] not in reached:
                reached.add(span[-1])
                queue.append((span[-1],path+span))
        for direction in range(4):
            nxt = neighbor(board, pos, direction)
            if nxt is None or nxt in reached:
                continue
            kind = cells[nxt]["kind"]
            gates = {"gateA":{"leverA"}, "gateB":{"leverB"}, "gateBoth":{"leverA","leverB"}}
            if kind in allowed or (kind == "gearPeg" and states[nxt]) or (kind in gates and gates[kind] <= open_levers):
                reached.add(nxt)
                queue.append((nxt,path+[nxt]))
            elif kind in {"gearPeg","bridgePeg",*gates}:
                stop, blocked = path, nxt
    if mode == "gears" and goal in reached:
        width = board["width"]
        parity = (start % width + start // width - goal % width - goal // width) % 2
        clockwise = cells[start]["clockwise"] ^ bool(states[start]) ^ bool(parity)
        return result(powered, "" if clockwise == board["clockwise"] else "spin", goal)
    return result(powered if mode == "gears" else stop, mode, blocked)


def simulate(board, moves):
    changes = iter(moves)
    states = [next(changes) if c["states"] > 1 else 0 for c in board["cells"]]
    start = next(i for i,c in enumerate(board["cells"]) if c["kind"] == "source")
    if board["mode"] in {"light","delivery"}:
        return travel(board, states, start)
    return connected(board, states, start)
