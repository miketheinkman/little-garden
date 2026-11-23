"""Repeatable tabletop activities for the family lesson shelf."""
import json
from pathlib import Path
import random

from .audio import clip_path


CONTENT = json.loads((Path(__file__).resolve().parents[1] / "content/table_games.json").read_text())
GAMES = CONTENT["lessons"]


def face(label, **details):
    return {"label": str(label), **details}


def pairs(topic):
    if topic in {"letters", "case", "teams", "words"}:
        pool = CONTENT["letters" if topic == "case" else topic]
        return [(face(s), face(s.lower() if topic == "case" else s)) for s in pool]
    if topic in {"colors", "shapes"}:
        return [(face(name, symbol=symbol),) * 2 for symbol, name in CONTENT[topic]]
    if topic == "count":
        return [(face(text, clip=clip_path("directions", text), spoken=text),) * 2 for text in CONTENT["counts"]]
    if topic == "melody":
        return [(face(label, clip=f"sounds/melody-{i}.ogg"),) * 2 for i, (label, _) in enumerate(CONTENT["melodies"])]
    if topic == "sums":
        return [(face(f"{a} + {b}"), face(a + b)) for a, b in [(1, 1), (1, 2), (2, 2), (2, 3), (3, 3)]]
    return [(face(i), face(i, symbol="●" * i, dots=True) if topic == "dots" else face(i)) for i in range(1, 6)]


def table_lesson(key, variation):
    spec = GAMES[key]
    tool = spec["tool"]
    rng = random.Random(f"{key}/{variation}")
    items = []
    if tool == "balance":
        for index in range(5):
            weights = [1, 2, 3, 4][:3 + int(index >= 2)]
            rng.shuffle(weights)
            target = weights[0] if index < 2 else sum(weights[:2])
            rng.shuffle(weights)
            animals = index in {1, 3, 4}
            blocks = [dict(weight=w, icon=CONTENT["animals"][w-1] if animals else "") for w in weights]
            items.append(dict(target=target, blocks=blocks, answer=str(target), choices=[], level=1 + int(index >= 2),
                              prompt=CONTENT["prompts"]["animals" if animals else "blocks"]))
    else:
        for i, topic in enumerate(spec["topics"]):
            deck = []
            for pair, cards in enumerate(rng.sample(pairs(topic), [2, 2, 3, 3, 4][i])):
                deck.extend(dict(card, pair=pair) for card in cards)
            rng.shuffle(deck)
            items.append(dict(deck=deck, listening=topic in {"count", "melody"}, prompt=CONTENT["prompts"][topic],
                              choices=[], answer="", level=1 + i // 2))
    return dict(title=spec["title"], skill=spec["skill"], age="4–8", category=spec["category"], level=1, strand=spec["strand"],
                participation="Independent", kind=tool, tool=tool, items=items)


def table_answer(item, encoded):
    pieces = item.get("deck") or item["blocks"]
    valid_ids = {str(i) for i in range(len(pieces))}
    fields = encoded.split(",", len(pieces))
    if any(s not in valid_ids for s in fields):
        return False
    if len(set(fields)) != len(fields):
        return False
    selected = [pieces[int(s)] for s in fields]
    if "blocks" in item:
        return sum(block["weight"] for block in selected) == item["target"]
    return len(selected) == len(pieces) and all(a["pair"] == b["pair"] for a, b in zip(selected[::2], selected[1::2]))
