import json
import random
from pathlib import Path
from string import ascii_uppercase

CONTENT = json.loads((Path(__file__).resolve().parents[1] / "content/discovery.json").read_text())
DISCOVERY = CONTENT["lessons"]
PATCH = "my-letters-v1"
DEFAULT_LETTERS = "SATPM"


def letter_selection(raw):
    """Accept a single set, including lower case and parent-friendly separators."""
    clean = "".join(ch for ch in raw if ch not in " ,\t\n\r")
    if not clean or not clean.isascii() or not clean.isalpha():
        raise ValueError("Choose one or more letters from A to Z.")
    return "".join(dict.fromkeys(clean.upper()))


def options(rng, correct, pool, count=3):
    distractors = [value for value in pool if value != correct]
    choices = [correct, *rng.sample(distractors, min(len(distractors), count - 1))]
    rng.shuffle(choices)
    return choices


def discovery_round(key, variation, letters=None):
    if letters is None:
        letters = "".join(random.Random(f"patch/{variation}").sample(ascii_uppercase, 5)) if key == PATCH and variation >= 32 else DEFAULT_LETTERS
    title, skill, age, category, strand, level, tool = DISCOVERY[key]
    rng = random.Random(f"{key}/{variation}/{letters}")
    animals = CONTENT["animals"]
    if variation >= 32 and tool in {"animal-id", "animal-word"}:
        animals = dict(animals)
        for icon, name in zip("🦁 🐯 🐻 🐺 🦊 🐼 🐨 🦌 🫎 🐑 🐐 🐄 🦇 🐜 🪱 🐌 🐋 🦭 🦢 🦀 🐙 🐢 🦦 🦓 🐎 🐍 🦫 🦬 🦎 🐪".split(),
                              "lion tiger bear wolf fox panda koala deer moose sheep goat cow bat ant worm snail whale seal swan crab octopus turtle otter zebra horse snake beaver bison lizard camel".split(), strict=True):
            animals[name] = [icon, ""]
    if tool == "sort":
        items = []
        for rule in rng.sample(CONTENT["sorts"], 5):
            groups = rule["groups"]
            if variation >= 32 and rule["bins"] == ["Letters","Numbers"]:
                groups = [[(ch, ch) for ch in alphabet] for alphabet in (ascii_uppercase, "0123456789")]
            pieces = [dict(icon=icon, name=name, bin=i) for i, group in enumerate(groups, 1)
                      for icon, name in rng.sample(group, 2)]
            rng.shuffle(pieces)
            items.append(dict(prompt=rule["prompt"], bins=rule["bins"], pieces=pieces, choices=[], answer=""))
    elif tool == "letter-patch":
        # A custom selection defines the entire practice set.
        targets = list(letters)
        rng.shuffle(targets)
        items = []
        for letter in targets:
            candidates = letters if len(letters) >= 2 else ascii_uppercase
            items.append(dict(answer=letter, prompt=f"Find the {letter} key.", choices=options(rng, letter, candidates)))
    elif tool == "gap":
        items = []
        for start in rng.sample(range(23), 5):
            run = list(ascii_uppercase[start:start+4])
            blank = rng.randrange(4) if variation >= 32 else rng.choice([1, 2, 3])
            letter = run[blank]
            run[blank] = "＿"
            items.append(dict(prompt="Say the letters in order. Which letter fills the empty stone?",
                              display="   ".join(run), choices=options(rng, letter, ascii_uppercase), answer=letter))
    else:
        items = []
        pool = [name for name, (_, call) in animals.items() if call] if tool == "calls" else list(animals)
        if tool == "animal-word":
            pool = [name for name in pool if len(name) <= 5]
        for animal in rng.sample(pool, 5):
            icon, clue = animals[animal]
            if tool == "animal-word":
                missing = rng.randrange(len(animal))
                letter = animal[missing]
                items.append(dict(prompt="Listen to the animal name. Which letter is missing?", word=animal,
                                  fragment=" ".join(animal[:missing] + "_" + animal[missing+1:]), icon=icon,
                                  choices=options(rng, letter, "abcdefghijklmnopqrstuvwxyz"), answer=letter))
            else:
                choices = options(rng, animal, list(animals))
                prompt = "Listen to the animal call. Which animal makes that sound?" if tool == "calls" else f"Can you find the {animal}?"
                items.append(dict(prompt=prompt, choices=choices, answer=animal, clue=clue,
                                  call=f"sounds/animals/{animal}.ogg" if tool == "calls" else "",
                                  animals=[dict(name=name, icon=animals[name][0]) for name in choices]))
    return dict(title=title, skill=skill, category=category, age=age, strand=strand, level=level, tool="" if tool in {"gap", "letter-patch"} else tool,
                kind="key" if key == PATCH else "choice", participation="Independent", items=items, **({"letters":letters} if key == PATCH else {}))
