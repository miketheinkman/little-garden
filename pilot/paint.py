"""Generate five paint challenges and keep their palettes in the saved lesson round."""
import json
import random
from pathlib import Path

STUDIO = json.loads((Path(__file__).resolve().parents[1] / "content/paint_studio.json").read_text())
PAINT_LESSONS = STUDIO["lessons"]


def swatch(name):
    return {"name": name, "color": STUDIO["colors"][name]}


def paint_lesson(key, variation):
    rng = random.Random(f"{key}/{variation}")
    spec = PAINT_LESSONS[key]
    tool = spec["tool"]
    items = []
    basics = ["red", "yellow", "blue", "orange", "green", "purple"]
    if tool == "paint-mix":
        blends, tints = STUDIO["recipes"][:3], STUDIO["recipes"][3:]
        targets = [recipe[2] for recipe in rng.sample(blends, 3) + rng.sample(tints, 2)]
    else:
        targets = rng.sample(basics, 5)
    for step, target in enumerate(targets):
        prompt = STUDIO["prompts"][tool]
        extra = {}
        if tool == "paint-mix":
            parts = basics[:3]
            if step >= 3:
                parts.append("white")
                prompt = STUDIO["prompts"]["tint"]
            extra["recipes"] = [dict(first=a, second=b, result=swatch(c)) for a, b, c in STUDIO["recipes"]
                                if a in parts and b in parts]
        else:
            parts = [target, *rng.sample([name for name in basics if name != target], 2 + int(step >= 3))]
        rng.shuffle(parts)
        items.append(dict(prompt=prompt.format(color=target), target=swatch(target), answer=target,
                          choices=[] if tool == "paint-mix" else parts, paints=[swatch(p) for p in parts], **extra))
    return dict(**spec, items=items, category="Art & drawing", kind="choice", strand="Color mixing" if tool == "paint-mix"
                else "Color recognition", participation="Independent")


def mixture_matches(item, state):
    lookup = {str(i): paint["name"] for i, paint in enumerate(item["paints"])}
    indices = state.split(",", 2)
    if len(indices) != 2 or any(i not in lookup for i in indices):
        return False
    ingredients = {lookup[i] for i in indices}
    return any(ingredients == {r["first"], r["second"]} and r["result"]["name"] == item["answer"]
               for r in item["recipes"])
