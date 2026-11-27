"""Choose interchangeable, already voiced examples without changing the skill being graded."""
import re
from functools import lru_cache
from itertools import chain
from random import Random

from .audio import has_audio
from .practice import build_round, round_count
from .question_sets import identity
from .themes import themed_round

MOUSE_CONTEXT_PROMPT = "Find the picture and tap it."


# The basket controls allow up to twelve objects in every theme.
def focused_basket_items():
    for count in (0, *range(6, 13)):
        prompt = (f"Add {count} items, then check your collection." if count
                  else "Leave the collection empty, then check it. That is zero items.")
        yield dict(prompt=prompt, answer=str(count), choices=[], display="")


def extra_examples(group):
    if group == "berry-basket":
        yield from focused_basket_items()
    elif group == "animal-lookout":
        animals = {"rabbit":"🐇", "elephant":"🐘", "monkey":"🐒", "kangaroo":"🦘",
                   "giraffe":"🦒", "jellyfish":"🪼", "penguin":"🐧", "hedgehog":"🦔"}
        for animal in animals:
            rng = Random(animal)
            choices = rng.sample([name for name in animals if name != animal],2) + [animal]
            rng.shuffle(choices)
            yield dict(prompt=f"Can you find the {animal}?", choices=choices, answer=animal, clue="", call="",
                       animals=[dict(name=name,icon=animals[name]) for name in choices])


def extended_piles(template, rng):
    for small in range(13):
        for large in range(small+1, 13):
            if small >= 1 and large <= 6:
                continue  # Already covered by the regular bank.
            piles = [small, large]
            rng.shuffle(piles)
            yield dict(template, piles=piles, answer="left" if piles[0] > piles[1] else "right")


# These items are self-contained. Preserve the original step's role where two
# answers teach opposite concepts, or where a game introduces harder boards.
EXAMPLE_GROUPS = set("""
animal-lookout animal-calls animal-words backspace signs sentence rhymes magic-e
living left-right inside-outside over-under left-right-pics sort-baskets color-baskets
letter-dots number-dots letter-memory picture-memory sound-memory seesaw clock
money-id money-total coins measure more harvest berry-basket holiday-clues holiday-traditions
color mirror draw real-imaginary
""".split())
KEEP_ANSWER = {"living", "real-imaginary", "left-right", "inside-outside", "over-under", "left-right-pics", "more"}
WORDS_FROM_ANSWER = {"animal-lookout", "animal-calls", "backspace", "signs", "sentence", "rhymes",
                     "magic-e", "holiday-clues", "holiday-traditions"}
NUMBER_WORDS = "zero one two three four five six seven eight nine ten".split()


INTEREST_WORDS = {
    "space": {"moon","rocket","star","planet","robot"},
    "ocean": {"crab","fish","octopus","seal","shell","whale"},
    "woodland": {"bear","deer","fox","owl","pine","squirrel"},
    "farm": {"apple","barn","chicken","cow","goat","horse","pig","tractor"},
    "garden": {"bee","beetle","carrot","flower","leaf","seed","snail","worm"},
    "trains": {"engine","rail","track","train"},
    "construction": {"brick","cone","crane","truck"},
    "bakery": {"bread","cake","cookie","muffin","pie"},
    "dinosaurs": {"dinosaur","fossil","triceratops"},
}


def interests(words):
    return words | {name for name,nouns in INTEREST_WORDS.items() if nouns & words}


def concepts(group, item):
    """Describe the content on the board, never instructions or distractor labels."""
    words = []
    numbers, letters, colors, shapes = set(), set(), set(), set()
    if group in WORDS_FROM_ANSWER:
        words.append(item["answer"])
    if group in {"color","mirror","draw"}:
        words.append(item["shape"].removeprefix("theme:"))
        shapes.add(words[-1])
    if group == "real-imaginary":
        words.extend(item["prompt"].split(".")[0].split())
    for field in ("word", "noun", "place", "stem"):
        if item.get(field):
            words.append(item[field])
    if group == "living":
        words.append(item["specimen"])
    if group == "left-right":
        side = int(item["answer"] == "right")
        words.append(item["sides"][side]["label"])
    for piece in item.get("pieces", ()):
        words.append(piece["name"])
        if "color" in piece:
            colors.add(piece["color"])
            shapes.add(piece["name"])
    for card in item.get("deck", ()):
        label = card["label"].lower()
        if "spoken" in card:
            for word in re.findall("[a-z]+",card["spoken"].lower())[-1:]:
                if word in NUMBER_WORDS:
                    numbers.add(str(NUMBER_WORDS.index(word)))
        elif not item["listening"]:
            words.append(label)
            colors.add(label)
            shapes.add(label)
            if label.isdecimal():
                numbers.add(label)
    for dot in item.get("dots", ()):
        label = dot["label"]
        (numbers if label.isdecimal() else letters).add(label.upper())
    numbers.update(map(str, item.get("piles", ())))
    for field in ("target", "price", "length", "hour_position", "carrots", "rabbits"):
        if field in item and str(item[field]).isdecimal():
            numbers.add(str(item[field]))
    if group == "harvest":
        numbers.add(str(item["carrots"] // item["rabbits"]))
    if group == "berry-basket":
        numbers.add(item["answer"])
    if group == "money-id":
        words.extend(m["name"] for m in item["money"] if m["mark"] == item["answer"])
        numbers.add(item["answer"].strip("$¢"))
    if group == "sort-baskets":
        descriptors = {w for piece in item["pieces"] for w in piece["name"].lower().split()}
        colors.update(descriptors)
        shapes.update(descriptors)
    for coin in item.get("handful", ()):
        numbers.add(str(coin["cents"]))
        words.append(coin["name"])
    if group == "money-total" and item["answer"].endswith("¢"):
        numbers.add(item["answer"][:-1])
    tokens = {w for phrase in words for w in re.findall("[a-z]+",phrase.lower())
              if w not in {"a","an","the","is","of","in","to","and"}}
    vocabulary = tokens | {w.lower() for w in words}
    initial = {w[0].upper() for w in tokens}
    digraphs = {w[:2].upper() for w in tokens if w.startswith(("sh","ch","th"))}
    return {"letters": letters | initial | digraphs, "numbers": numbers, "colors": colors,
            "shapes": shapes, "vocabulary": vocabulary, "interests": interests(vocabulary)}


def role(group, item, step):
    if group in KEEP_ANSWER:
        return item["answer"]
    if "deck" in item:
        return step, item["prompt"], len(item["deck"])
    if group == "seesaw":
        return step, item["level"], item["prompt"]
    if group == "sort-baskets":
        return tuple(item["bins"])
    if group == "color-baskets":
        return len(item["bins"]), len(item["pieces"])
    if group == "animal-calls":
        return bool(item.get("call"))
    if group == "clock":
        return item["minute_position"]
    if group in {"letter-dots", "number-dots"}:
        return len(item["dots"])
    return None


@lru_cache(maxsize=64)
def example_bank(key, theme):
    group = key.rsplit("-v",1)[0]
    count = round_count(key)
    variations = Random(key).sample(range(count), min(count,48))
    bank = {}
    rounds = (themed_round(key,build_round(key,v),theme,v)["items"] for v in [0,*variations])
    extras = extra_examples(group)
    if group == "more":
        template = themed_round(key,build_round(key,0),theme,0)["items"][0]
        extras = extended_piles(template, Random(key))
    for items in chain(rounds,[extras]):
        for step,item in enumerate(items):
            item_role = role(group,item,step)
            signature = identity(group,item,step)
            # An outline can use different letter/number runs. Keep those options
            # even though only one instance of an outline belongs in a round.
            index = (item_role,signature,item["dots"][0]["label"] if "dots" in item else "")
            if index not in bank and has_audio(key,item):
                bank[index] = (item_role, signature, item, concepts(group,item))
    return tuple(bank.values())


def contextual_examples(key, theme, items, configs, rng):
    group = key.rsplit("-v",1)[0]
    configs = [(c["context"]/100, {field:set(c[field]) for field in
                ("letters","numbers","colors","shapes","vocabulary","interests") if c.get(field)})
               for c in configs if c.get("context")]
    if group not in EXAMPLE_GROUPS or not any(values for _,values in configs):
        return items
    offset = rng.random()
    used = {identity(group,item,i) for i,item in enumerate(items)}
    selected = []
    for i,item in enumerate(items):
        threshold = (offset + i/len(items)) % 1
        active = [values for strength,values in configs if threshold < strength]
        def matches(tags):
            return any(wanted & tags[field] for values in active for field,wanted in values.items())
        if active and not matches(concepts(group,item)):
            item_role = role(group,item,i)
            current = identity(group,item,i)
            candidates = [(sig,candidate) for r,sig,candidate,tags in example_bank(key,theme)
                          if r == item_role and (sig not in used or sig == current) and matches(tags)]
            if candidates:
                sig,item = rng.choice(candidates)
                used.add(sig)
        selected.append(item)
    return selected


# The prompts, artwork, materials and answers in these activities belong together.
# Select a complete authored variant that mentions the focus in its subject matter.
LINKED_GROUPS = {"book","snail","story","weather","beans","drums","shadow","scissors","sink-float"}
OFFLINE = {"beans","drums","shadow","scissors","sink-float"}


def linked_concepts(group, items):
    body = " ".join(item["prompt"] if group in OFFLINE else item.get("display","") for item in items).lower()
    tokens = set(re.findall(r"[a-z]+",body))
    counts = {str(i) for i,word in enumerate(NUMBER_WORDS) if word in tokens}
    counts.update(re.findall(r"\b\d+\b",body))
    if "twice" in tokens:
        counts.add("2")
    if "once" in tokens:
        counts.add("1")
    if group == "weather":
        counts.update(str(len(run)) for run in re.findall("☁+",body.replace("\ufe0f","")))
    # Offline instruction verbs and articles are not the subject matter of a lesson.
    subjects = tokens - set("a an the of at in on it is was and to from with he her his for had did she by has that or".split())
    return {"numbers":counts, "colors":tokens, "shapes":tokens, "vocabulary":tokens, "interests":interests(tokens),
            "letters": {word[0].upper() for word in subjects} if group in {"book","snail","story"} else set()}


def linked_examples(key,theme,items,configs,rng):
    group = key.rsplit("-v",1)[0]
    if group not in LINKED_GROUPS:
        return items
    chance = rng.random()
    active = [c for c in configs if chance < c.get("context",0)/100]
    def matches(candidate):
        tags = linked_concepts(group,candidate)
        return any(values.intersection(c.get(field,())) for c in active for field,values in tags.items())
    if not active or matches(items):
        return items
    count = round_count(key)
    for variation in rng.sample(range(count),min(count,24)):
        bank = themed_round(key,build_round(key,variation),theme,variation)["items"]
        if len(bank)==len(items) and matches(bank) and all(has_audio(key,item) for item in bank):
            return bank
    return items
