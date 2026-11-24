"""Repeat a skill with predictable, bounded variations. Round zero is the pilot original."""
import json
import random

from django.conf import settings

from .discovery import DISCOVERY, discovery_round
from .explorations import EXPLORATIONS, exploration_round
from .paint import PAINT_LESSONS, paint_lesson
from .puzzles import PUZZLES, route_lesson

from .table_games import GAMES, table_lesson

CONTENT = settings.BASE_DIR / "content"
LESSONS = json.loads((CONTENT / "lessons.json").read_text())
LESSONS.update({key: route_lesson(key) for key in PUZZLES})
LESSONS.update({key: table_lesson(key, 0) for key in GAMES})
LESSONS.update({key: paint_lesson(key, 0) for key in PAINT_LESSONS})
LESSONS.update({key: discovery_round(key, 0) for key in DISCOVERY})
LESSONS.update({key: exploration_round(key, 0) for key in EXPLORATIONS})
GARDEN_PRACTICE = json.loads((CONTENT / "garden_practice.json").read_text())
AUTHORED = json.loads((CONTENT / "variations.json").read_text())


# The original IDs remain available to saved assignments and feedback links.
FIVE_PROMPT_ROUNDS = json.loads((CONTENT / "five_prompt_rounds.json").read_text())
CURRENT_VERSION = {key.replace("-v2", "-v1"): key for key in FIVE_PROMPT_ROUNDS}
CURRENT_LESSONS = {}
for key, lesson in LESSONS.items():
    current = CURRENT_VERSION.get(key, key)
    if current in FIVE_PROMPT_ROUNDS:
        lesson = dict(lesson, items=lesson["items"] + FIVE_PROMPT_ROUNDS[current])
    CURRENT_LESSONS[current] = lesson
LESSONS.update(CURRENT_LESSONS)


def round_count(key):
    if key in GAMES or key in PAINT_LESSONS or key in DISCOVERY or key in EXPLORATIONS:
        return 32
    if key in PUZZLES:
        return 4
    if key in {"scissors-v1", "sink-float-v1"}:
        return 4
    return 1 + len(AUTHORED[key]) if key in AUTHORED else 1000


def options(rng, answer, pool):
    choices = [answer, *rng.sample(sorted(set(pool) - {answer}), 2)]
    rng.shuffle(choices)
    return list(map(str, choices))


def five_prompt_round(key, number, rng):
    original = build_round(key.replace("-v2", "-v1"), number)
    items = original["items"]
    first, second, third = [item["answer"] for item in items]
    if original["kind"] == "key":
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if key == "keys-v2" else "0123456789"
        fresh = rng.choice(sorted(set(pool) - {first, second, third}))
        extra = [
            dict(prompt=prompt, display=target, answer=target, choices=options(rng, target, pool))
            for prompt, target in [(f"Find {first} again.", first), (f"Can you find the {fresh} key?", fresh)]
        ]
    else:
        extra = []
        for item in items[:2]:
            # Count the same quantity in a different collection.
            pictures = [("🌼", "flowers"), ("🍃", "leaves"), ("🌱", "sprouts")]
            symbol, noun = rng.choice([pair for pair in pictures if pair[0] not in item["display"]])
            count = item["answer"]
            extra.append(dict(prompt=f"How many {noun} do you see?", display=" ".join([symbol] * int(count)),
                              answer=count, choices=options(rng, count, [first, second, third])))
    return dict(original, items=items + extra)


# The same word banks supply the bundled spoken examples.
SHORT_VOWEL_WORDS = {"a": ("cat", "map"), "e": ("hen", "net"), "i": ("pig", "fin"),
                     "o": ("pot", "fox"), "u": ("sun", "cup")}
DIGRAPH_WORDS = {"sh": ("ship", "shop", "shell"), "ch": ("chat", "chin", "chip"),
                 "th": ("thin", "thick", "thumb")}


def build_round(key, number):
    lesson = LESSONS[key]
    if number == 0:
        return lesson
    if key in EXPLORATIONS:
        return exploration_round(key, number)
    if key in DISCOVERY:
        return discovery_round(key, number)
    if key in PAINT_LESSONS:
        return paint_lesson(key, number)
    if key in GAMES:
        return table_lesson(key, number)
    if key in PUZZLES:
        return route_lesson(key, number % 4)
    rng = random.Random(f"{key}/{number}")
    if key in FIVE_PROMPT_ROUNDS:
        return five_prompt_round(key, number, rng)
    items = [item.copy() for item in lesson["items"]]
    if key in AUTHORED:
        for item, changes in zip(items, AUTHORED[key][number-1], strict=True):
            item.update(changes)
            if len(item["choices"]) > 1:
                item["choices"] = rng.sample(item["choices"], len(item["choices"]))
        return dict(lesson, items=items)
    if key in GARDEN_PRACTICE:
        # Keep paired investigations in order so prediction precedes observation.
        if key in {"scissors-v1", "sink-float-v1"}:
            pairs = list(zip(items, GARDEN_PRACTICE[key], strict=True))
            items = [dict(pair[(number >> i) & 1]) for i, pair in enumerate(pairs)]
        else:
            items = rng.sample(items + GARDEN_PRACTICE[key], len(items))
        return dict(lesson, items=items)
    group = key.removesuffix("-v1")
    if group in ("middle-sound", "digraphs"):
        words = SHORT_VOWEL_WORDS if group == "middle-sound" else DIGRAPH_WORDS
        for item, sound in zip(items, rng.sample(list(words), len(items))):
            item.update(word=rng.choice(words[sound]), answer=sound, choices=options(rng, sound, words))
    elif group == "case-match":
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        for item, letter in zip(items, rng.sample(alphabet, len(items))):
            item.update(keycap=letter.upper(), answer=letter, choices=options(rng, letter, alphabet))
    elif group == "lowercase":
        for item, letter in zip(items, rng.sample("abcdefghijklmnopqrstuvwxyz", len(items))):
            item.update(prompt=f"Start at the gold dot and trace lowercase {letter}.", answer=letter)
    elif group == "ten":
        for item, seeds in zip(items, rng.sample(range(1, 10), len(items))):
            left = 10 - seeds
            item.update(prompt=rng.choice(["How many more seeds will fill this tray?",
                                           "Count the empty spaces. How many seeds will fit?",
                                           "How many more seeds will make ten?"]),
                        seeds=seeds, answer=str(left), choices=options(rng, left, range(1, 10)))
    elif group == "harvest":
        # Include both group sizes, with whole shares and at most twelve counters.
        groups = [2, 3, rng.choice([2, 3])]
        rng.shuffle(groups)
        for item, rabbits in zip(items, groups):
            carrots = rabbits * rng.randint(2, 12 // rabbits)
            question = rng.choice(["Can you deal one to each rabbit in turn?",
                                   "How many carrots will each rabbit get?",
                                   "How can you check that each rabbit gets the same number?"])
            item.update(carrots=carrots, rabbits=rabbits,
                        prompt=f"Share {carrots} carrots equally between {rabbits} rabbits. {question}")
    elif group in ("keys", "number-keys", "sounds", "signs", "blend", "letters", "digits"):
        pools = {
            "keys": list("ABCDEFGHJKLMNPRSTUVWYZ"), "number-keys": list("0123456789"),
            "sounds": ["map", "fan", "dog", "net", "lip", "rug", "pot", "hen"],
            "signs": ["fern bed", "dig here", "sun hat", "bee box", "mud pie", "wet soil", "herb pot", "oak tree"],
            "letters": list("LVOWZN"), "digits": list("12347"),
        }
        word = rng.choice(["map", "sun", "fin", "red", "pot", "cup"])
        targets = list(word.upper()) if group == "blend" else rng.sample(pools[group], len(items))
        for index, (item, target) in enumerate(zip(items, targets)):
            if group in ("keys", "number-keys"):
                item.update(prompt=rng.choice(["Find the {} key.", "Can you press {}?", "Look for {} on your keyboard."]).format(target),
                            display=target, answer=target, choices=options(rng,target,pools[group]))
            elif group == "sounds":
                initial = target[0].upper()
                item.update(prompt=f'Say “{target}” slowly. Which letter do you hear at the start?',
                            answer=initial, choices=options(rng,initial,list("MFDNLRPH")))
            elif group == "signs":
                item.update(prompt=rng.choice(["Copy this sign for the garden.", "Type the label, including its space."]), display=target,answer=target)
            elif group == "blend":
                position = ["first","middle","last"][index]
                item.update(prompt=f'Say “{word}”. Choose the letter for its {position} sound.',
                            display=" ".join(word[:index]+"_"*(3-index)),answer=target,choices=options(rng,target,targets))
            else:
                item.update(answer=target,prompt=f"Start at the dot and follow the strokes to form {target}.")
        if group == "blend":
            lesson = dict(lesson,title=f"Build {word}")
    elif group in ("count1", "count2", "five", "berry-basket", "market", "tens"):
        low, high = {"count1":(1,3),"count2":(3,5),"five":(1,4),"berry-basket":(1,5),
                     "market":(1,5),"tens":(2,8)}[group]
        for index, (item, n) in enumerate(zip(items, rng.sample(range(low, high+1), len(items)))):
            if group.startswith("count"):
                thing = rng.choice(["🌱","🌼","🍃"])
                item.update(prompt=rng.choice(["Count each picture once. How many are there?", "How many can you count in this group?"]),
                            display=" ".join([thing]*n),answer=str(n),choices=options(rng,n,range(low,high+1)))
            elif group == "five":
                item.update(prompt=rng.choice(["Five spots in the seed tray. How many are empty?", "How many more seeds would fill this tray?", "Count the open spaces. How many seeds fit there?"]),display="● "*n+"○ "*(5-n),
                            answer=str(5-n),choices=options(rng,5-n,range(1,6)))
            elif group == "berry-basket":
                item.update(prompt=rng.choice(["Pick {} berries for the picnic.", "Can you fill an order for {} berries?"]).format(n), answer=str(n))
            elif group == "market":
                m=rng.randint(1,5)
                orders = [f"Pack {n} berries for Jay and {m} for Kit. Fill their basket.",
                          f"The baker needs {n} berries for jam and {m} more for pie. Pack the order.",
                          f"Put {m} berries in the basket, then add {n} more for a friend."]
                item.update(prompt=orders[index], answer=str(n+m))
            else:
                ones=rng.randint(1,9)
                if index == 0:
                    total = n*10 + ones
                    prompt = "Each bag holds ten seeds. How many seeds are in this order?"
                    display = f"{n} full bags + {ones} loose"
                elif index == 1:
                    total = n+1
                    prompt = "Bundle the ten loose seeds. How many full bags do you have now?"
                    display = f"{n} full bags + 10 loose"
                else:
                    total = 10+ones
                    prompt = "Open one bag of ten. How many seeds are loose now?"
                    display = f"{n} full bags + {ones} loose"
                item.update(prompt=prompt, display=display, answer=str(total),
                            choices=options(rng,total,[total,total+1,total-1,total+2]))
    elif group == "ladybugs":
        for item, x in zip(items,rng.sample(range(12,78),len(items))):
            item.update(x=x,y=rng.randint(12,67),prompt=rng.choice(["Can you spot the ladybug?", "Tap the ladybug where it landed.", "Click the little red beetle."]))
    elif group in ("lines","river"):
        for item in items:
            bend=rng.randint(14,55)
            item.update(path=f"M20 85 Q60 {85-bend*1.4:.0f} 100 75 T180 {75+bend}",
                        prompt=rng.choice(["Follow the bend from the gold dot.", "Hold at the dot and steer along the trail."]))
    elif group == "pattern":
        a,b=rng.sample(["🌿","🌻","🍎","🌷"],2)
        for item,unit in zip(items,[[a,b],[a,a,b],[a,b,b]]):
            seq=(unit*3)[:rng.randint(4,7)]
            item.update(prompt="Follow the repeating group. Which picture comes next?",display=" ".join(seq)+" …",answer=unit[len(seq)%len(unit)],choices=rng.sample([a,b],2))
    elif group == "weather":
        days=["Monday","Tuesday","Wednesday"]
        nums=rng.sample(range(1,6),3)
        chart=" · ".join(f"{day} {'☁️'*n}" for day,n in zip(days,nums))
        for item,op,name in zip(items[:2],[max,min],["most","fewest"]):
            item.update(prompt=f"Which day had the {name} cloud marks?",display=chart,answer=days[nums.index(op(nums))],choices=rng.sample(days,3))
        diff=max(nums)-min(nums)
        items[2].update(prompt="How many more marks did the cloudiest day have than the clearest day?",display=chart,answer=str(diff),choices=options(rng,diff,range(1,6)))
    else:
        raise ValueError(f"Missing practice generator for {key}")
    return dict(lesson,items=items)
