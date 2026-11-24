"""Present one saved practice round in a learner's chosen setting."""
import json
import random

from .practice import CONTENT, LESSONS

THEMES = json.loads((CONTENT / "themes.json").read_text())
MAGIC_PICTURES = {"cape":"🦸","kite":"🪁","cube":"🧊","cane":"🦯","tube":"🧪","pane":"🪟",
                  "tape":"📼","code":"💻","note":"📝","ride":"🚲","pine":"🌲","bone":"🦴","mane":"🐴"}
THEME_CHOICES = [(key, world["label"]) for key, world in THEMES.items()]


def lesson_title(key, original, w):
    actor, unit = w["actor"]["name"], w["one"]
    names = {
        "water-works": f"Water Works at the {w['site']}", "train-tracks": f"Train Tracks to the {w['site']}",
        "ladybugs": f"{actor.capitalize()} lookout", "count1": f"Count the {w['many']}",
        "count2": f"Count a bigger set of {w['many']}", "beans": "Five real counters",
        "berry-basket": f"Fill the {w['box']}", "market": f"Orders at the {w['site']}",
        "harvest": f"Share the {w['many']}", "pattern": f"{w['place'].capitalize()} patterns",
        "tens": f"Bundle the {w['many']}", "signs": f"Type the {w['place']} signs",
        "river": f"Follow the {actor} trail", "snail": f"Delivery at the {w['site']}",
        "story": f"The last {unit}", "weather": f"{w['place'].capitalize()} picture log",
        "color": f"Color the {w['place']}", "mirror": f"Mirror at the {w['site']}",
        "measure": f"Measure with {w['many']}", "coins": f"Coins at the {w['site']}",
        "rhymes": f"Rhymes at the {w['site']}", "blend": "Build a word",
    }
    return names.get(key, original)


def summary(key, lesson, theme):
    if theme not in THEMES or theme == "garden":
        return lesson
    w = THEMES[theme]
    group = key.rsplit("-v", 1)[0]
    result = dict(lesson, title=lesson_title(group, lesson["title"], w), world=w, world_key=theme)
    if group == "harvest":
        result.update(skill=f"Give each {w['friend']['name']} an equal share",
                      prep=f"Take turns dealing one {w['one']} at a time. Use the screen or up to 12 small counters.")
    elif group == "beans":
        result["prep"] = f"Use five small counters as {w['many']} and five empty cups."
    elif group == "shift":
        result["skill"] = f"Capitalize a name at the {w['site']} with Shift"
    elif group == "case-match":
        result["skill"] = "Match uppercase keys to lowercase labels"
    elif group == "lowercase":
        result["skill"] = f"Form lowercase letters on the {w['line']}"
    elif group == "backspace":
        result["skill"] = f"Erase an extra letter on a {w['place']} label"
    elif group == "arrow-maze":
        result["skill"] = f"Steer the {w['actor']['name']} with arrow keys"
    elif group in {"more", "twos", "measure", "coins", "clock", "living", "sentence"}:
        result["skill"] = {"more":"Compare two groups", "twos":"Count objects in pairs",
                           "measure":"Measure length with equal units", "coins":"Pay an exact price with coins",
                           "clock":"Read the clock for daily tasks", "living":"Classify living things and objects",
                           "sentence":"Build a sentence to describe a scene"}[group]
    return result


def themed_round(key, lesson, theme, variation=0):
    result = summary(key, lesson, theme)
    if result is lesson:
        return lesson
    w = THEMES[theme]
    group = key.rsplit("-v", 1)[0]
    rng = random.Random(f"{theme}/{key}/{variation}")
    items = [dict(item) for item in lesson["items"]]
    for index, item in enumerate(items):
        style_item(group, item, w, variation, index, rng)
    return dict(result, items=items)


def style_item(group, it, w, variation, i, rng):
    actor, friend, prop = w["actor"]["name"], w["friend"]["name"], w["prop"]["name"]
    site, one, many, icon = w["site"], w["one"], w["many"], w["cargo_icon"]
    label = w["labels"][(i + variation) % len(w["labels"])]
    a = it["answer"]
    # These new sequences were authored as units. Replacing individual steps can
    # change the characters, target word, or materials midway through the task.
    if it.get("bank_context") and group not in {"color","mirror","draw","number-check","key-check"}:
        return
    if group in {"keys", "number-keys"}:
        it["prompt"] = f"Find the {a} key on the {site} keyboard."
    elif group == "case-match":
        it["prompt"] = f"Which lowercase label at the {site} matches this key?"
    elif group in {"lines", "river", "letters", "digits", "lowercase"}:
        it["prompt"] = (f"Guide the {actor} along the path from the gold dot." if group in {"lines", "river"} else
                        f"Start at the dot and trace {a} on the {w['line']}.")
    elif group == "ladybugs":
        it.update(prompt=f"Find and tap the {actor}.", target=actor, icon=w["actor"]["icon"])
    elif group in {"count1", "count2"}:
        it.update(prompt=f"Count the {many}. How many do you see?", display=" ".join([icon] * int(a)))
    elif group in {"five", "ten"}:
        it["prompt"] = f"How many more {many} will fill all {'five' if group == 'five' else 'ten'} spaces?"
        if group == "five":
            it["display"] = " ".join([icon] * (5-int(a)) + ["○"] * int(a))
    elif group == "number-check":
        if i == 0:
            it.update(prompt=f"How many {many}?", display=" ".join([icon] * int(a)))
        elif i == 1:
            it.update(prompt=f"How many more {many} will make five?", display=" ".join([icon]*(5-int(a)) + ["○"]*int(a)))
        else:
            it["prompt"] = f"Each bundle holds ten {many}. How many are here?"
            it["display"] = f"{int(a)//10} full bundles + {int(a)%10} loose"
    elif group in {"market", "berry-basket", "tens"}:
        if group == "berry-basket":
            it["prompt"] = f"Put {a} {one if a == '1' else many} in the {w['box']}."
        else:
            for field in ("prompt", "display"):
                it[field] = (it.get(field, "").replace("berries", many).replace("seeds", many)
                             .replace("basket", w["box"]).replace("for jam", "for Kit").replace("for pie", "for Jay")
                             .replace("The baker", "The helper"))
    elif group == "harvest":
        it["prompt"] = f"Share {it['carrots']} {many} equally between {it['rabbits']} helpers at the {site}. How many does each get?"
    elif group == "beans":
        it["prompt"] = f"Use five counters as {many}. Place one in each cup at the {site}, then count together."
    elif group == "pattern":
        symbols = list(dict.fromkeys(it["choices"]))
        mapped = dict(zip(symbols, [icon, w["other"]["icon"], w["goal"]["icon"]], strict=False))
        it.update(prompt=f"What comes next in the {site} pattern?", display=" ".join(mapped.get(x,x) for x in it["display"].split()),
                  choices=[mapped[x] for x in it["choices"]], answer=mapped[a])
    elif group in {"signs","key-check"}:
        if group == "signs" or i == 2:
            if variation >= 1000 or it.get("bank_context"):
                label = a
            it.update(prompt=f"Copy the sign for the {site}. Include the space.", display=label, answer=label)
        else:
            it["prompt"] = f"Type this {'letter' if i == 0 else 'word'} on the {site} keyboard."
    elif group == "middle-sound":
        it.update(word=it["word"] if variation >= 1000 else w["vowels"][a], prompt=f"Listen to the {friend}’s word. Which letter makes the middle sound?")
    elif group == "digraphs":
        it.update(word=it["word"] if variation >= 1000 else w["digraphs"][a], prompt=f"Listen to the {friend}’s word. Which letter pair makes its first sound?")
    elif group == "sounds" and variation >= 1000:
        it["prompt"] = f"Listen with the {friend}. Which letter makes the first sound?"
    elif group == "sounds" or (group == "sound-check" and i == 0):
        word = list(w["vowels"].values())[(variation+i)%5]
        initial = word[0].upper()
        choices = [initial, *rng.sample(sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")-{initial}), 2)]
        rng.shuffle(choices)
        it.update(word=word, answer=initial, choices=choices, prompt=f"Listen with the {friend}. Which letter makes the first sound?")
    elif group == "sound-check":
        word = w["vowels"][a.lower()] if i == 1 else w["digraphs"][a.lower()]
        it.update(word=word, prompt="Which letter makes the middle sound?" if i == 1 else "Which pair makes the first sound?")
    elif group == "blend" and variation >= 1000:
        return
    elif group == "blend":
        word = list(w["vowels"].values())[variation%5]
        answer = word[i].upper()
        choices = [answer, *rng.sample(sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")-{answer}), 2)]
        rng.shuffle(choices)
        position = ("first", "middle", "last")[i]
        it.update(prompt=f'Say “{word}” with the {friend}. Choose its {position} letter.',
                  display=" ".join(word[:i]+"_"*(3-i)), answer=answer, choices=choices)
    elif group == "magic-e":
        word = w["magic"][(variation+i)%len(w["magic"])]
        choices = [word, *rng.sample(sorted(set(MAGIC_PICTURES)-{word}), 2)]
        rng.shuffle(choices)
        it.update(stem=word[:-1], answer=word, choices=choices,
                  pictures=[{"label":x,"icon":MAGIC_PICTURES[x]} for x in choices],
                  prompt=f"Add a silent e to the {site} label. Which picture matches the new word?")
    elif group in {"shift","backspace","syllables","rhymes"} and variation >= 1000:
        return
    elif group == "rhymes":
        if i == variation % 4:
            word, answer, picture = w["rhyme"]
            others = [p for p in it["pictures"] if p["label"] != answer and p["label"] != a]
            pictures = [{"label":answer,"icon":picture}, *others]
            rng.shuffle(pictures)
            it.update(word=word, answer=answer, choices=[p["label"] for p in pictures], pictures=pictures)
        it["prompt"] = f"Listen at the {site}. Which picture rhymes with the word?"
    elif group == "syllables":
        it.update(word=w["beats"][a], prompt=f"Say the {site} word. Tap once for each syllable.")
    elif group == "shift":
        name = w["names"][(variation+i)%len(w["names"])]
        distractors = rng.sample(sorted(set("abcdefghijklmnopqrstuvwxyz") - {name[0].lower()}),2)
        letters = [name[0].lower(), *distractors]; rng.shuffle(letters)
        it.update(prompt=f"At the {site}, write {name} with a capital {name[0]}. Hold Shift and press the letter.",
                  name_tail=name[1:], answer=name[0], letters=letters)
    elif group == "backspace":
        word = label.split()[i%2]
        it.update(prompt=f'The {site} label should say “{word}.” Erase the extra letter.', label=word+word[-1], answer=word)
    elif group == "arrow-maze":
        it["prompt"] = f"Steer the {actor} to the {w['goal']['name']}. Use the arrow keys or the arrows below."
    elif group == "left-right":
        sides = [w["unit"],w["other"]] if (i+variation)%2 == 0 else [w["goal"],w["prop"]]
        it.update(sides=[dict(label=p["name"], icon=p["icon"]) for p in sides],
                  prompt=f'Grown-up, say “Use your {a} hand to touch the {sides[a == "right"]["name"]} on the {a}.”')
    elif group == "scissors":
        shape = "straight" if i == 0 else "curved"
        it["prompt"] = f"Draw a {shape} path to the {site} on scrap paper. Help your child snip along it."
    elif group == "drums":
        it["prompt"] = f"Take turns at the {site}. " + it["prompt"]
    elif group == "book":
        name = w["names"][variation % len(w["names"])]
        it.update(display=f"Sam sat. {name} ran to Sam. Sam had a map.",prompt="Read together. Who had the map? Point to the words that tell you.")
    elif group == "snail":
        destination = w["labels"][variation % len(w["labels"])]
        scenes = [(f'At the {site}, Pip finds a box marked “Take me to the {destination}.” The door is closer.',
                   "Where should Pip take the box?", f"The {destination}", ["The door","Pip’s home"]),
                  (f"On the way, rain starts to fall. Pip pulls a cover over the box and keeps going.",
                   "Why does Pip cover the box?", "To keep it dry", ["To hide it from a friend","To carry more"]),
                  (f"At the {destination}, Kit lifts the lid and smiles at Pip.", "Which clue shows Kit opened the box?",
                   "Kit lifts the lid", ["Pip walks away","Rain falls"])]
        text,q,ans,other = scenes[i]; choices=[ans,*other]; rng.shuffle(choices)
        it.update(prompt=q,display=text,answer=ans,choices=choices)
    elif group == "story":
        it.update(display=(f"Kit has one {one} left at the {site}. A friend reaches for it too." if i == 0 else
                           f"Kit says, “You go first.” The friends take turns with the {one}."),
                  prompt=("What do you think Kit will do next?" if i == 0 else "How did Kit help a friend? Tell a different ending."))
    elif group == "shadow":
        it["prompt"] = (f"Pretend a toy is visiting the {site}. Predict how its shadow changes when it moves toward a flashlight."
                        if i == 0 else "Keep the light still. Move the toy toward the light, then toward the wall. Compare the shadows.")
    elif group == "weather":
        it["display"] = it["display"].replace("☁️",icon)
        it["prompt"] = (it["prompt"].replace("cloud marks","marks").replace("clouds","marks")
                        .replace("cloudiest day","day with the most marks").replace("clearest day","day with the fewest marks"))
    elif group in {"color","mirror","draw"}:
        shape = w["art"][variation % len(w["art"])]
        it.update(shape="theme:"+shape, starter=group=="draw")
        it["prompt"] = {"color":f"Choose your colors and fill the {shape} outline.",
                        "mirror":f"Finish the {shape} design. Reflect the left half across the dotted line.",
                        "draw":f"These marks started a {shape}. Turn them into a picture of your own."}[group]
    elif group == "sentence":
        candidates = [scene for scene in w["sentences"] if len(scene["text"].split()) == len(it["tiles"])]
        scene = candidates[(variation+i)%len(candidates)]
        words = scene["text"].split()
        tiles = words.copy()
        rng.shuffle(tiles)
        if tiles == words:
            tiles = tiles[1:] + tiles[:1]
        it.update(scene=scene["scene"], scene_alt=scene["text"]+".", answer=scene["text"], tiles=tiles, also_accept=[])
    elif group == "more":
        it["prompt"] = f"Which pile has more {many}?"
    elif group == "twos":
        it["prompt"] = f"Gather the {many} in pairs. Count by twos. How many are there?"
    elif group == "measure":
        obj = w["straight"] if it["object"] == "carrot" else w["bent"]
        it.update(measure_name=obj,prompt=f"Lay {many} end to end along the {obj}. How many long is it?")
    elif group == "coins":
        it["prompt"] = f"The {prop} costs {it['price']} cents at the {site}. Pay the exact price."
    elif group == "clock":
        task = [f"open the {site}", f"pack the {w['box']}", f"put away the {prop}"][i]
        it["prompt"] = f"Time to {task}! Which time does the clock show?"
    elif group == "sink-float":
        it["prompt"] = f"Set up a test at your pretend {site}. " + it["prompt"]
    elif group == "living":
        specimen = w["living"] if a=="Living" else w["inert"]
        it.update(specimen=specimen["name"], icon=specimen["icon"], prompt=f"At the {site}, which crate does this {specimen['name']} belong in?")


def assignment_lesson(row, current_theme=None):
    raw = row.round_snapshot or LESSONS[row.lesson]
    theme = raw.get("_opened_theme")
    if theme is None:
        theme = "garden" if row.step or row.retries or row.completed else current_theme or row.learner.lesson_theme
    return themed_round(row.lesson, raw, theme, row.variation)
