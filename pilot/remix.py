"""Question banks for new rounds. Saved rounds retain their original generator and snapshot."""
import json
from pathlib import Path
from string import ascii_uppercase

from .art import THEME_SHAPES
from .discovery import options

BANK = json.loads((Path(__file__).resolve().parent.parent / "content/practice_bank.json").read_text())
VOWELS = {key: value.split() for key, value in BANK["vowels"].items()}
DIGRAPHS = {key: value.split() for key, value in BANK["digraphs"].items()}
CVC = [word for group in VOWELS.values() for word in group]
NAMES = BANK["names"].split()


def number_choices(rng, n, pool):
    return options(rng, str(n), list(map(str, pool)))


def sign(rng):
    return rng.choice(BANK["sign_starts"].split()) + " " + rng.choice(BANK["sign_ends"].split())


def maze(rng):
    # Carve a connected maze on the player's five-column grid.
    board = ["#"] * 25
    start = rng.choice([0, 4, 20, 24])
    stack = [start]
    depth = {start: 0}
    board[start] = "B"
    while stack:
        cell = stack[-1]
        x, y = cell % 5, cell // 5
        neighbors = [(ny*5+nx) for nx, ny in ((x-2,y),(x+2,y),(x,y-2),(x,y+2))
                     if 0 <= nx < 5 and 0 <= ny < 5 and ny*5+nx not in depth]
        if not neighbors:
            stack.pop()
            continue
        neighbor = rng.choice(neighbors)
        depth[neighbor] = depth[cell]+1
        board[(cell+neighbor)//2] = board[neighbor] = "."
        stack.append(neighbor)
    goal = max(depth, key=depth.get)
    board[goal] = "L"
    return dict(maze="".join(board), answer=str(goal))


def guided(group, items, index, rng):
    """Each sequence shares its props, question and outcome within one round."""
    if group == "snail":
        who, where, _ = BANK["deliveries"][index % 6]
        gift = BANK["parcel_goods"][index // 6 % 5]
        route = [(f"Pip has {gift} for {who}. The label says to meet at the {where}.",
                  "Where should Pip go?", f"The {where}", ["The gate", "The bench"]),
                 (f"The wind tugs at the parcel. Pip tucks it into a bag and carries on.",
                  "Why does Pip use a bag?", "To keep the parcel safe", ["To take a nap", "To catch the wind"]),
                 (f"At the {where}, {who} takes out {gift} and thanks Pip.",
                  "What did Pip deliver?", gift.capitalize(), [s.capitalize() for s in BANK["parcel_goods"] if s != gift])]
        for item, (display, prompt, answer, others) in zip(items, route):
            item.update(display=display, prompt=prompt, answer=answer, choices=options(rng,answer,others))
    elif group == "book":
        name = BANK["read_names"][index % 6]
        action, noun = BANK["read_events"][index//6 % 6]
        items[0].update(display=f"{name} {action}. Look at the {noun}!", prompt="Read together. Who did it? Point to the name.")
    elif group == "story":
        pair = BANK["story_pairs"][index//6 % 5]
        for item, passage in zip(items, pair):
            item["display"] = passage.format(object=BANK["story_objects"][index%6])
        items[0]["prompt"] = "Read together. What could the friends do next?"
        items[1]["prompt"] = "How did the friends solve the problem? Tell another ending."
    elif group == "beans":
        arrangement = ["a row", "a circle", "a zigzag", "a cross", "two small groups"][index % 5]
        start = ["the nearest cup", "the farthest cup", "any cup you choose", "the cup your grown-up points to",
                 "the cup closest to your left hand", "the cup beside your right hand"][index // 5 % 6]
        items[0]["prompt"] = f"Arrange five cups in {arrangement}. Start with {start}. Put one bean in each cup and count all five."
    elif group == "drums":
        a = BANK["rhythm"][index % 6]
        b = [v for v in BANK["rhythm"] if v != a][index//6 % 5]
        items[0]["prompt"] = f"Ask a grown-up to {a} twice, then {b} once. Echo the pattern."
        items[1]["prompt"] = f"Your turn to lead. Make a pattern with these two movements: {a} and {b}."
    elif group == "shadow":
        obj, (move, feature) = BANK["shadows"][index%6], BANK["shadow_changes"][index//6 % 5]
        items[0]["prompt"] = f"Shine a light at a wall. Hold {obj} in the beam. Predict what happens if it moves {move}."
        items[1]["prompt"] = f"Try that movement with your grown-up. What do you notice about the shadow’s {feature}?"
    elif group == "scissors":
        shape, paper = BANK["snips"][index%6], BANK["cuts"][index//6 % 5]
        items[0]["prompt"] = f"Ask a grown-up to draw {shape} on {paper}. Point along one path before cutting."
        items[1]["prompt"] = f"Use child-safe scissors with your grown-up. Snip along the {shape} you traced."
    elif group == "sink-float":
        a,b = rng.sample(BANK["water_items"],2)
        items[0]["prompt"] = f"With a grown-up, find {a} and {b}. Predict which will float in a bowl of water."
        items[1]["prompt"] = "Test the two items one at a time. Where did each stop? Compare with your prediction."
    elif group in {"color","mirror","draw"}:
        shape = list(THEME_SHAPES)[index % len(THEME_SHAPES)]
        items[0].update(shape="theme:"+shape, art_shift_x=(-2, 0, 2)[index//2 % 3], art_shift=index//6 % 5-2,
                        starter=group=="draw", starter_window=index % 4, prompt={"color":f"Choose your colors and fill the {shape} outline.",
                        "mirror":f"Finish the {shape} design. Reflect the left half across the dotted line.",
                        "draw":f"These marks started a {shape}. Turn them into a picture of your own."}[group])
    elif group == "number-check":
        n, planted, total = rng.randint(1,5), rng.randint(0,5), rng.randint(10,59)
        for item, (value, display, prompt) in zip(items, [
            (n,"● "*n,"Count these seeds."),(5-planted,"● "*planted+"○ "*(5-planted),"How many spaces are empty?"),
            (total,f"{total//10} bags of ten + {total%10} loose","Each bag holds ten seeds. How many seeds are here?")]):
            item.update(answer=str(value),display=display,prompt=prompt,choices=number_choices(rng,value,range(max(0,value-2),value+3)))
    elif group == "key-check":
        for item,target in zip(items,(ascii_uppercase[(7 * index + 11) % 26],rng.choice(CVC),sign(rng))):
            item.update(display=target,answer=target)
    elif group == "sound-check":
        word = rng.choice(CVC)
        vowel, pair = rng.choice(list(VOWELS)), rng.choice(list(DIGRAPHS))
        for item,(target,w,prompt,pool) in zip(items,[(word[0].upper(),word,"Which letter starts the word?",ascii_uppercase),
                (vowel.upper(),rng.choice(VOWELS[vowel]),"Which vowel is in the middle?","AEIOU"),
                (pair.upper(),rng.choice(DIGRAPHS[pair]),"Which letter pair starts the word?",["SH","TH","CH"])]):
            item.update(answer=target,word=w,prompt=prompt,choices=options(rng,target,pool))
    for item in items:
        item["bank_context"] = True


def garden_item(group, item, rng):
    if group == "arrow-maze":
        item.update(maze(rng))
    elif group == "more":
        a,b = rng.sample(range(1,7),2)
        item.update(piles=[a,b],answer="left" if a>b else "right")
    elif group == "twos":
        n = rng.randint(1,7)
        item.update(pairs=n,answer=str(n*2),choices=number_choices(rng,n*2,range(1,15)))
    elif group == "measure":
        n = rng.randint(1,6)
        item.update(length=n,answer=str(n))
    elif group == "coins":
        n = rng.randint(1,30)
        item.update(price=n,answer=str(n),prompt=f"The seed packet costs {n} cents. Put that amount on the counter.")
    elif group == "clock":
        hour, minute = rng.randint(1,12), rng.choice([0,30])
        time = f"{hour}:{minute:02}"
        item.update(hour_angle=hour%12*30+minute/2, minute_angle=minute*6, hour_position=str(hour) if not minute else
                    f"halfway between {hour} and {hour%12+1}", minute_position="6" if minute else "12",
                    answer=time,choices=options(rng,time,[f"{h}:{m:02}" for h in range(1,13) for m in (0,30)]))
    elif group == "shift":
        name = rng.choice(NAMES)
        item.update(name_tail=name[1:],answer=name[0],letters=options(rng,name[0].lower(),ascii_uppercase.lower()),
                    prompt=f"Hold Shift and type the first letter of {name}.")
    elif group == "backspace":
        word = rng.choice(BANK["labels"].split())
        item.update(label=word+rng.choice("abcdefghijklmnopqrstuvwxyz"),answer=word,prompt=f"Fix the label. Erase the extra letter after {word}.")
    elif group == "syllables":
        n = rng.choice(list(BANK["beats"]))
        item.update(word=rng.choice(BANK["beats"][n].split()),answer=n)
    elif group == "rhymes":
        target, answer, icon = rng.choice(BANK["rhymes"])
        # Only one option may rhyme, including when two entries share an ending.
        others = [r for r in BANK["rhymes"] if r[1][-2:] != answer[-2:] and r[1] != target]
        pics = [(answer,icon)] + [(r[1],r[2]) for r in rng.sample(others,2)]
        rng.shuffle(pics)
        item.update(word=target,answer=answer,pictures=[dict(label=k,icon=v) for k,v in pics], choices=[k for k,v in pics])
    elif group == "sentence":
        animal, icon = rng.choice(BANK["scene_animals"])
        verb, target, picture = rng.choice(BANK["scene_actions"])
        words = [animal, verb, target]
        tiles = rng.sample(words, len(words))
        if tiles == words:
            tiles = tiles[1:] + tiles[:1]
        sentence = " ".join(words)
        item.update(scene=f"{icon} {picture}", scene_alt=sentence+".", answer=sentence,
                    tiles=tiles, also_accept=[], bank_context=True)
    elif group == "left-right":
        props = rng.sample(BANK["specimens"]["Non-living"], 2)
        side = rng.choice(("left", "right"))
        name = props[int(side == "right")][0]
        item.update(sides=[dict(label=label, icon=icon) for label, icon in props], answer=side,
                    prompt=f"With your {side} hand, touch the {name} on the {side}.", bank_context=True)
    elif group == "living":
        name, icon = rng.choice(BANK["specimens"][item["answer"]])
        item.update(specimen=name, icon=icon, prompt="Which crate does this belong in?", bank_context=True)
    elif group == "magic-e":
        pictures = BANK["silent_e"]
        word = rng.choice(list(pictures))
        labels = options(rng, word, list(pictures))
        item.update(stem=word[:-1], answer=word, choices=labels, bank_context=True,
                    pictures=[dict(label=name, icon=pictures[name]) for name in labels])
    return item


def garden_round(group, items, rng):
    fields = {
        "arrow-maze": "maze", "rhymes": "word", "syllables": "word", "more": "piles",
        "left-right": "sides", "living": "specimen",
    }
    field = fields.get(group, "answer")
    seen = set()
    result = []
    for source in items:
        for _ in range(24):
            item = garden_item(group, source.copy(), rng)
            target = json.dumps(item[field], sort_keys=True)
            if target not in seen:
                break
        seen.add(target)
        result.append(item)
    return result
