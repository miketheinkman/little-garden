"""Five-question picture, listening, and sequencing rounds."""
import json
import random
from pathlib import Path
from string import ascii_uppercase

from .discovery import options

DATA = json.loads((Path(__file__).resolve().parents[1] / "content/explorations.json").read_text())
EXPLORATIONS = DATA["lessons"]
MONEY = [dict(name=name, cents=value, material=material,
              mark=f"${value // 100}" if material == "bill" else f"{value}¢")
         for name, value, material in DATA["money"]]


def holiday_questions(rng, traditions):
    offset = 3 if traditions else 0
    rows = DATA["holidays"]
    items = []
    for row in rng.sample(rows, 5):
        answer = row[offset]
        pool = [r[offset] for r in rows]
        if traditions and answer == "a plate of sweets":
            pool.remove("a pumpkin pie")
        labels = options(rng, answer, pool)
        icons = {r[offset]: r[offset+1] for r in rows}
        items.append(dict(prompt=row[5 if traditions else 2], answer=answer, choices=labels,
                          pictures=[dict(label=name, icon=icons[name]) for name in labels]))
    return items


def color_sort(rng):
    colors = rng.sample(list(DATA["colors"]), 2)
    pieces = [dict(name=shape, icon=DATA["shapes"][shape], color=color, ink=DATA["colors"][color], bin=i)
              for i, color in enumerate(colors, 1) for shape in rng.sample(list(DATA["shapes"]), 2)]
    rng.shuffle(pieces)
    return dict(prompt="Put each shape into the basket that matches its color.", pieces=pieces,
                bins=[dict(label=color.capitalize(), ink=DATA["colors"][color]) for color in colors], choices=[], answer="")


def twins(rng, odd):
    symbols = rng.sample(["🐸", "🐢", "🐌", "🦋", "🐞", "🐝", "🦗", "🐛"], 3)
    faces = [symbols[0], symbols[1], symbols[1] if odd else symbols[2]]
    rng.shuffle(faces)
    return dict(prompt="Which picture is different from the other two?" if odd else "Which picture is the same as the one above?",
                sample="" if odd else symbols[0], faces=faces, choices=[], answer=str(faces.index(symbols[0])))


def dots(rng, name, letters, step):
    coords = DATA["outlines"][name]
    start = 0 if letters else 1
    if step >= 2:
        start = rng.randrange(27 - len(coords)) if letters else rng.randrange(1, 6)
    labels = list(ascii_uppercase[start:start+len(coords)]) if letters else [str(start+i) for i in range(len(coords))]
    nodes = [dict(x=x, y=y, label=label) for (x, y), label in zip(coords, labels)]
    return dict(prompt="Connect the dots in alphabet order." if letters else "Connect the dots in counting order.",
                dots=nodes, outline=name, choices=[], answer=",".join(str(i) for i in range(len(nodes))))


def arithmetic(rng, subtract):
    a = rng.randint(2, 9) if subtract else rng.randint(1, 6)
    b = rng.randint(1, a) if subtract else rng.randint(1, 10-a)
    total = a-b if subtract else a+b
    return dict(prompt="Some are crossed out. How many are left?" if subtract else "Put the two groups together. How many altogether?",
                left=list(range(total if subtract else a)), right=list(range(b)), equation=f"{a} {'−' if subtract else '+'} {b}",
                subtract=subtract, answer=str(total), choices=options(rng, str(total), list(map(str, range(11)))))


def amount(cents):
    return f"${cents//100}.{cents%100:02}" if cents >= 100 else f"{cents}¢"


def count_money(rng, step):
    handful = rng.choices(MONEY[:4], k=rng.randint(2, 4))
    if step >= 2:
        handful.insert(0, rng.choice(MONEY[4:]))
    total = sum(piece["cents"] for piece in handful)
    choices = options(rng, amount(total), [amount(total+i) for i in (-10, -5, -1, 1, 5, 10, 100) if total+i >= 0])
    return dict(prompt="Count the money on the tray. How much is there?", handful=handful, choices=choices, answer=amount(total))


def money_id(rng):
    targets = rng.sample(MONEY[:4], 3) + rng.sample(MONEY[4:], 2)
    rng.shuffle(targets)
    items = []
    for target in targets:
        others = [piece for piece in MONEY if piece != target]
        tray = rng.sample(others, 2) + [target]
        rng.shuffle(tray)
        items.append(dict(prompt=f"Which one is the {target['name']}?", money=tray, choices=[], answer=target["mark"]))
    return items


def compare(rng, pair, target, step):
    order = rng.sample(pair, 2)
    return dict(prompt=f"Choose the picture where the object is {target}.", variants=order, choices=[],
                answer=target, specimen=["🌻","🌲","🕯️","🌵","🏠"][step])


def position(rng, pair, target, step):
    order = rng.sample(pair, 2)
    if pair[0] == "inside":
        icon, noun, place = [("🧃","juice","fridge"),("🧸","bear","box"),("🍎","apple","fridge"),
                              ("⚽","ball","box"),("🥛","milk","fridge")][step]
    elif pair[0] == "under":
        icon, noun, place = [("🦋","butterfly"),("🐝","bee"),("🐦","bird"),("🎈","balloon"),("🪁","kite")][step] + ("bridge",)
    else:
        icon, noun, place = [("🐈","cat"),("🐕","dog"),("🐇","rabbit"),("🦊","fox"),("🐦","bird")][step] + ("tree",)
    relation = f"to the {target} of" if target in ("left", "right") else target
    return dict(prompt=f"Which picture shows the {noun} {relation} the {place}?", variants=order, choices=[], answer=target,
                specimen=icon, noun=noun, place=place)


def exploration_round(key, variation):
    title, skill, age, category, strand, level, tool = EXPLORATIONS[key]
    rng = random.Random(f"{key}/{variation}")
    if tool == "pictures":
        items = holiday_questions(rng, key == "holiday-traditions-v1")
    elif tool == "dots":
        shapes = rng.sample(list(DATA["outlines"]), 5)
        shapes.sort(key=lambda name: len(DATA["outlines"][name]))
        items = [dots(rng, name, key == "letter-dots-v1", step) for step, name in enumerate(shapes)]
    elif tool == "money-id":
        items = money_id(rng)
    elif tool == "listen-number":
        items = [dict(prompt="Listen to the number. Which numeral matches?", word=DATA["number_words"][n],
                      answer=str(n), choices=options(rng, str(n), list(map(str, range(13)))))
                 for n in rng.sample(range(13), 5)]
    elif tool == "pretend":
        stories = [(scene, label) for group, label, count in (("real", "Real life", 3 if variation%2 else 2),
                   ("pretend", "Make-believe", 2 if variation%2 else 3)) for scene in rng.sample(DATA[group], count)]
        rng.shuffle(stories)
        items = [dict(prompt=f"{sentence} Could that really happen?", specimen=icon, choices=["Real life","Make-believe"], answer=label)
                 for (icon,sentence),label in stories]
    elif tool in {"position", "compare"}:
        pair = {"big-small-v1":("big","small"), "tall-short-v1":("tall","short"), "over-under-v1":("under","over"),
                "left-right-pics-v1":("left","right"), "inside-outside-v1":("inside","outside")}[key]
        targets = [*pair, *pair, rng.choice(pair)]
        rng.shuffle(targets)
        make = compare if tool == "compare" else position
        items = [make(rng, pair, target, i) for i,target in enumerate(targets)]
    elif tool == "sort":
        items = [color_sort(rng) for _ in range(5)]
    elif tool == "twins":
        items = [twins(rng, (step+variation)%2) for step in range(5)]
    elif tool == "arithmetic":
        items = [arithmetic(rng, key == "take-away-v1") for _ in range(5)]
    else:
        items = [count_money(rng, step) for step in range(5)]
    return dict(title=title, skill=skill, age=age, category=category, strand=strand, level=level, tool=tool,
                kind="choice", participation="Independent", items=items)
