"""Repeat a skill with predictable, bounded variations. Round zero is the pilot original."""
import json
import random

from django.conf import settings

CONTENT = settings.BASE_DIR / "content"
LESSONS = json.loads((CONTENT / "lessons.json").read_text())
AUTHORED = json.loads((CONTENT / "variations.json").read_text())


def round_count(key):
    return 1 + len(AUTHORED[key]) if key in AUTHORED else 1000


def options(rng, answer, pool):
    choices = [answer, *rng.sample(sorted(set(pool) - {answer}), 2)]
    rng.shuffle(choices)
    return list(map(str, choices))


def build_round(key, number):
    lesson = LESSONS[key]
    if number == 0:
        return lesson
    rng = random.Random(f"{key}/{number}")
    items = [item.copy() for item in lesson["items"]]
    if key in AUTHORED:
        for item, changes in zip(items, AUTHORED[key][number-1], strict=True):
            item.update(changes)
            if len(item["choices"]) > 1:
                item["choices"] = rng.sample(item["choices"], len(item["choices"]))
        return dict(lesson, items=items)
    group = key.removesuffix("-v1")
    if group in ("keys", "number-keys", "sounds", "signs", "blend", "letters", "digits"):
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
