"""Apply sparse learner preferences to existing, authored and voiced activities."""
import random
import json
from itertools import cycle
from functools import lru_cache
from math import log
from .audio import has_audio
from .focus_context import MOUSE_CONTEXT_PROMPT, contextual_examples, extended_piles, extra_examples, linked_examples
from collections import defaultdict

from django.core import signing
from django.db.models import Q
from django.http import Http404
from django.utils import timezone

from .discovery import PATCH, discovery_round
from .practice import build_round, round_count
from .question_sets import identity
from .skills import COLOR, LETTER, NUMBER, OPERATORS, PATHS, SOUND, direct_target, known_targets, objectives
from .themes import themed_round

# Only standalone prompts may be exchanged. Linked stories, multi-tier check-ins,
# construction sequences and tools whose stages depend on position stay intact.
TARGETS = {**dict.fromkeys(LETTER, "letters"), **dict.fromkeys(SOUND, "letters"),
           **dict.fromkeys(NUMBER | {"five", "ten", "more", "market", "add-groups", "take-away", "harvest", "measure", "coins"}, "numbers"),
           **dict.fromkeys(COLOR, "colors"), "animal-lookout": "vocabulary", "animal-calls": "vocabulary",
           "same-different": "shapes", "syllables": "vocabulary", "rhymes": "vocabulary"}
FACET = {"letters": "letters", "numbers": "numbers", "colors": "colors", "vocabulary": "words"}
MIX = {**dict.fromkeys(("keys","my-letters","number-keys","shift","backspace","signs","copy-word"),"Keyboard"),
       "case-match": "Matching", "blend": "Phonics",
       "letters": "Tracing", "lowercase": "Tracing", "digits": "Tracing",
       **dict.fromkeys(SOUND,"Phonics")}
# Neutral, equivalent pictures in the counting groups, size comparison or card back.
# Their tags never enter direct_target.
PROPS = [
    ("🍎", "apple", "red", "circle", "farm"), ("🌙", "moon", "yellow", "crescent", "space"),
    ("⭐", "star", "yellow", "star", "space"), ("🐚", "shell", "pink", "", "ocean"),
    ("🦖", "dinosaur", "green", "", "dinosaurs"), ("🪵", "log", "brown", "", "woodland"),
    ("🚂", "train", "red", "", "trains"), ("🧁", "muffin", "pink", "", "bakery"),
    ("🚧", "barrier", "yellow", "", "construction"), ("🌻", "sunflower", "yellow", "", "garden"),
    ("🔺", "triangle", "red", "triangle", ""), ("🟦", "square", "blue", "square", ""),
    ("🟢", "circle", "green", "circle", ""), ("🔶","diamond","orange","diamond",""),
    ("🎄","tree","green","triangle","christmas"),
]
CONTEXT_SLOTS = {"add-groups", "take-away", "big-small", "tall-short", "letter-memory", "picture-memory", "sound-memory"}
AUTO_LETTERS = "SATPINMDGOCKEURHBFLJWXYZQV"
AUTO_NUMBERS = list(map(str, range(1,21))) + ["0"]
AUTO_COLORS = ["red","blue","yellow","green","orange","purple"]
AUTO_SHAPES = ["circle","square","triangle","star","diamond"]

def active_configs(child, day=None):
    day = day or timezone.localdate()
    rows = child.focuses.filter(paused=False).filter(Q(starts=None)|Q(starts__lte=day),
                                                     Q(ends=None)|Q(ends__gte=day)).order_by("pk")
    result = []
    known = None
    for row in rows:
        config = dict(row.config)
        if row.automatic:
            if known is None:
                known = known_targets(child)
            # Advancement uses demonstrated direct evidence for each correspondence.
            # A letter seen in a name, or traced, does not establish decoding readiness.
            for field, sequence, objective, facet, size in [
                ("letters", AUTO_LETTERS, "sounds","sounds",2),
                ("numbers", AUTO_NUMBERS, "hear-number","numbers",2),
                ("colors", AUTO_COLORS, "name-paint","colors",1),
                ("shapes", AUTO_SHAPES, "same-different","shapes",1),
            ]:
                if field not in config:
                    pending = []
                    for value in sequence:
                        evidence = (objective,facet,value)
                        if field=="letters":
                            if value in "AEIOU":
                                evidence = ("middle-sound","sounds",value)
                            elif frozenset([value]) not in supported_targets("sounds-v1",child.lesson_theme):
                                evidence = ("keys","letters",value)
                        if evidence not in known:
                            pending.append(value)
                    if pending:
                        config[field] = pending[:size]
            config["automatic"] = True
            config["advanced_decoding"] = any(obj == "magic-e" for obj,_,_ in known)
            config["known_sounds"] = sorted({v.split(" · ")[0] for obj,facet,v in known if facet=="phonemes" and obj in SOUND})
        if config.get("name_letters") and not row.config.get("letters"):
            familiar = {v for obj,facet,v in known or () if obj in {"keys","my-letters"} and facet=="letters"}
            config["name_keys"] = sorted((set(child.nickname.upper()) & set(AUTO_LETTERS)) - familiar)
        if config:
            result.append(config)
    return result


def applicable(config, objective):
    subject, branch = PATHS[objective]
    if config.get("subjects") and subject not in config["subjects"]:
        return False
    if config.get("objectives") and objective not in config["objectives"]:
        return False
    if config.get("branches") and branch not in config["branches"]:
        return False
    if config.get("operators") and subject == "Math" and OPERATORS.get(objective) not in config["operators"]:
        return False
    if objective in {"keys","my-letters"} and config.get("name_keys"):
        return True
    domains = {name for name in ("letters","numbers","colors","shapes","vocabulary") if config.get(name)}
    broad = config.get("subjects") or config.get("branches") or config.get("objectives") or (objective in OPERATORS and config.get("operators"))
    return bool(TARGETS.get(objective) in domains or (not domains and broad))


def activity_weight(config, obj):
    return config.get("weights",{}).get(MIX.get(obj,"Other activities"),1)


# Whole three-sound words with a one-to-one letter/sound correspondence.
# Keep the three linked steps together and reuse recorded, authored prompts.
DECODABLE = set("sat mat map sun fin red pot cup tap pat sit pin tin nip tip pan nap sad mad dog log dig mud".split())


def permitted_blend(key, number, theme, known):
    for v in [number, 0, *range(1,32)]:
        raw = build_round(key,v)
        presented = themed_round(key,raw,theme,v)
        word = "".join(i["answer"].lower() for i in presented["items"])
        if word in DECODABLE and set(word.upper()) <= known:
            return raw,presented
    return None


def target_facet(obj,domain):
    if obj in SOUND:
        return "sounds"
    if obj in {"animal-lookout","animal-calls"}:
        return "animals"
    return FACET.get(domain,domain)


@lru_cache(maxsize=128)
def bank_variations(key):
    count = round_count(key)
    return (0, *random.Random(key).sample(range(count),min(count,64)))


@lru_cache(maxsize=256)
def supported_targets(key,theme):
    obj = objectives(key)[0]
    if obj == "same-different":
        return {frozenset([shape]) for shape in AUTO_SHAPES}
    field = target_facet(obj,TARGETS.get(obj))
    result = set()
    for variation in bank_variations(key):
        bank = themed_round(key,build_round(key,variation),theme,variation)
        for step,item in enumerate(bank["items"]):
            values = direct_target(key,item,step)["facets"].get(field,[])
            if values and has_audio(key,item):
                result.add(frozenset(values))
    result.update(frozenset([item["answer"]]) for item in extra_examples(obj) if has_audio(key,item))
    if obj == "more" and result:
        result.update(frozenset((str(a), str(b))) for a in range(13) for b in range(a+1,13))
    return result


def can_anchor(obj):
    # The child can compare a focused pile with a companion, or split a
    # focused amount even when every operand is not itself a focus number.
    return obj in {"more","harvest","five","ten","market","add-groups","take-away"}


def lesson_weight(key, configs, theme="garden"):
    total = 0
    for c in configs:
        for obj in objectives(key):
            if not applicable(c,obj):
                continue
            weight = activity_weight(c,obj)
            wanted = set(c.get(TARGETS.get(obj),[]))
            if weight and wanted and len(objectives(key)) == 1:
                if not any(values <= wanted or (can_anchor(obj) and values & wanted) for values in supported_targets(key,theme)):
                    continue
            total += weight
    return total


def policy_for(child, key, purpose="practice", *, configs=None, mode=None):
    configs = active_configs(child) if configs is None else configs
    if not configs:
        return {}
    obj = objectives(key)[0]
    configs = [dict(c, letters=c["name_keys"]) if obj in {"keys","my-letters"} and c.get("name_keys") else c for c in configs]
    policy = {"configs":configs, "theme":child.lesson_theme, "mode":mode or ("only" if any(c.get("mode")=="only" and applicable(c,obj) for c in configs) else "mixed")}
    if TARGETS.get(obj) and any(applicable(c,obj) for c in configs):
        recent = []
        previous = child.assignment_set.filter(lesson=key,step__gt=0).order_by("-pk").values_list(
            "round_snapshot","step")[:2]
        group = key.rsplit("-v",1)[0]
        for snapshot, completed_steps in previous:
            if snapshot:
                recent.extend(json.dumps(identity(group,item,index),sort_keys=True)
                              for index,item in enumerate(snapshot["items"][:completed_steps]))
        if recent:
            policy["recent"] = recent
    if TARGETS.get(obj) and purpose == "practice" and policy["mode"] != "only":
        known = {t for t in known_targets(child) if t[0] == obj}
        if obj in {"keys","my-letters"}:
            known.update((obj,"letters",v) for c in configs for v in c.get("familiar",[]))
        policy["known"] = sorted(known)
    return policy


def token(child, key, policy):
    return signing.dumps([child.pk,key,policy],salt="lesson-focus",compress=True)


def read_token(child, key, value):
    try:
        pk, lesson, policy = signing.loads(value,salt="lesson-focus")
    except (ValueError, TypeError, signing.BadSignature) as exc:
        raise Http404 from exc
    if pk != child.pk or lesson != key:
        raise Http404
    return policy


def contextual_words(items, configs, key, theme, rng):
    # Reuse complete recorded syllable prompts, matching the original beat count.
    # This keeps the correct number, difficulty and drum interaction identical.
    strength = max((c.get("context",0) for c in configs if c.get("letters") or c.get("vocabulary")),default=0)
    if not strength:
        return items
    used = {item["word"] for item in items}
    by_beats = defaultdict(dict)
    for v in rng.sample(range(round_count(key)),min(round_count(key),16)):
        for candidate in themed_round(key,build_round(key,v),theme,v)["items"]:
            word = candidate["word"]
            if any(c.get("context") and (word[:1].upper() in c.get("letters",[]) or word in c.get("vocabulary",[])) for c in configs):
                by_beats[candidate["answer"]][word] = candidate
    result = []
    for item in items:
        candidates = [v for word,v in by_beats[item["answer"]].items() if word not in used and has_audio(key,v)]
        if candidates and rng.random() < strength/100:
            item = rng.choice(candidates)
            used.add(item["word"])
        result.append(item)
    return result


def context_prop(configs, rng, *, allow_symbols=False):
    chance = rng.random()
    candidates = []
    for config in configs:
        if chance >= config.get("context",0)/100:
            continue
        letters = config.get("letters",())
        for icon, word, color, shape, interest in PROPS:
            if (any(word.upper().startswith(letter) for letter in letters) or
                    word in config.get("vocabulary",()) or color in config.get("colors",()) or
                    shape in config.get("shapes",()) or interest in config.get("interests",()) or
                    word in config.get("interests",())):
                candidates.append((icon,word))
        if allow_symbols:
            candidates.extend((v,v) for field in ("letters","numbers") for v in config.get(field,()))
    return rng.choice(candidates) if candidates else (None,None)


def contextual_patterns(items, configs, rng):
    result = []
    seen = {identity("pattern",item,i) for i,item in enumerate(items)}
    for index,item in enumerate(items):
        symbol, _ = context_prop(configs,rng,allow_symbols=True)
        if symbol and symbol not in item["choices"]:
            old = rng.choice(item["choices"])
            replace = lambda value: symbol if value == old else value
            candidate = dict(item, choices=[replace(v) for v in item["choices"]],
                             answer=replace(item["answer"]),
                             display=" ".join(replace(v) for v in item["display"].split()))
            if identity("pattern",candidate,index) not in seen:
                item = candidate
        result.append(item)
        seen.add(identity("pattern",item,index))
    return result


def compile_round(key, number, letters, policy):
    raw = discovery_round(key,number,letters) if letters and key == PATCH else build_round(key,number)
    if not policy:
        return raw
    theme = policy["theme"]
    configs = policy["configs"]
    lesson = themed_round(key, raw, theme, number)
    group = key.rsplit("-v",1)[0]
    auto = [c for c in configs if c.get("automatic") and any(c.get("weights",{"default":1}).values())]
    if group == "blend" and auto:
        known = {v for c in auto for v in c.get("known_sounds",[])}
        selected = permitted_blend(key,number,theme,known)
        if selected:
            raw, prepared = selected
            return dict(raw,items=prepared["items"],_focus_theme=theme,_opened_theme=theme,_set_round=True)
    obj = objectives(key)[0]
    domain = TARGETS.get(obj)
    eligible = [c for c in configs if applicable(c,obj) and activity_weight(c,obj)>0]
    wanted = {v for c in eligible for v in c.get(domain,[])}
    items = lesson["items"]
    rng = random.Random(f"focus/{key}/{number}/{theme}")
    notice = ""
    # No changes to a mixed diagnostic's mix of levels, or a parent's explicit letter selection.
    if wanted and group == "same-different":
        glyphs = {"circle":"●","square":"■","triangle":"▲","star":"★","diamond":"◆"}
        selected = sorted(wanted.intersection(glyphs))
        if selected:
            rng.shuffle(selected)
            if policy.get("mode") == "mixed":
                familiar = [v for o,f,v in policy.get("known",[]) if o==obj and f=="shapes" and v in glyphs and v not in selected]
                if familiar:
                    selected.append(rng.choice(familiar))
            ordered = cycle(selected)
            shaped = []
            for item in items:
                shape = next(ordered)
                correct = int(item["answer"])
                target = glyphs[shape]
                others = rng.sample([v for v in glyphs.values() if v != target],2)
                faces = others if item["sample"] else [others[0]]*2
                faces.insert(correct,target)
                candidate = dict(item, sample=target if item["sample"] else "", faces=faces, target_shape=shape)
                if not any(identity(group,old,0) == identity(group,candidate,0) for old in shaped):
                    shaped.append(candidate)
            items = shaped
    elif wanted and group not in ("sound-check","key-check","number-check") and not letters:
        facet = target_facet(obj,domain)
        known = {v for o,f,v in policy.get("known",[]) if o == obj and f == facet} - wanted
        direct, anchors, review = {}, {}, {}
        if group == "more" and wanted & {"0","7","8","9","10","11","12"} and has_audio(key,items[0]):
            for item in extended_piles(items[0],rng):
                pair = set(map(str,item["piles"]))
                if pair & wanted:
                    pool = direct if pair <= wanted else anchors
                    pool[identity(group,item,0)] = item
        for item in extra_examples(group):
            if item["answer"] in wanted and has_audio(key,item):
                direct[identity(group,item,0)] = item
        count = round_count(key)
        variations = [number,*rng.sample(range(count),min(count,16)),*bank_variations(key)]
        for v in variations:
            bank = themed_round(key, build_round(key,v), theme,v)
            for index, item in enumerate(bank["items"]):
                vals = set(direct_target(key,item,index)["facets"].get(facet,[]))
                if not vals or not has_audio(key,item):
                    continue
                ident = identity(group,item,index)
                if vals <= wanted or (policy.get("contains") and vals & wanted):
                    direct.setdefault(ident,item)
                elif can_anchor(obj) and vals & wanted:
                    anchors.setdefault(ident,item)
                elif vals <= known:
                    review.setdefault(ident,item)
            if len(direct) >= len(items)*3 and (not known or len(review)>=len(items)):
                break
        if not direct:
            direct = anchors
        if direct:
            n = len(items)
            picks = list(direct.values())
            rng.shuffle(picks)
            recent = set(policy.get("recent",[]))
            if recent:
                picks.sort(key=lambda item: json.dumps(identity(group,item,0),sort_keys=True) in recent)
            if review and policy.get("mode") != "only":
                picks = picks[:max(1,n-1)]
                picks.extend(rng.sample(list(review.values()),min(n-len(picks),len(review))))
            items = picks[:n]
            rng.shuffle(items)
        else:
            limits = {"more": "The two piles use different counts from 0 to 12.",
                      "berry-basket": "The basket holds 0 to 12 items.",
                      "harvest": "This activity splits up to 12 items evenly between two or three helpers."}
            notice = " ".join(filter(None, ("This activity has no available questions for these targets.",
                                            limits.get(group), "Showing its usual round.")))
    if not wanted:
        items = contextual_examples(key,theme,items,configs,rng)
        items = linked_examples(key,theme,items,configs,rng)
    if group == "syllables" and not wanted:
        items = contextual_words(items,configs,key,theme,rng)
    if group == "ladybugs":
        contextual = []
        for item in items:
            symbol, label = context_prop(configs,rng,allow_symbols=True)
            if symbol:
                candidate = dict(item,icon=symbol,target=label,prompt=MOUSE_CONTEXT_PROMPT)
                if has_audio(key,candidate):
                    item = candidate
            contextual.append(item)
        items = contextual
    if group == "pattern":
        items = contextual_patterns(items,configs,rng)
    if group in CONTEXT_SLOTS:
        contextual = []
        for item in items:
            icon, _ = context_prop(configs,rng,allow_symbols=group.endswith("-memory"))
            contextual.append(dict(item,context_icon=icon) if icon else item)
        items = contextual
    # Store presented items; applying theme transforms a second time can change phonics answers.
    if key == PATCH and wanted and not letters:
        raw = dict(raw,letters="".join(i["answer"] for i in items))
    if items == lesson["items"] and not notice:
        return raw
    return dict(raw, items=items, _focus_theme=theme, _opened_theme=theme, _set_round=True, focus_notice=notice)


def focus_rank(candidates, configs, child, seed):
    if not configs:
        return candidates
    rng = random.Random(f"focus-picks/{child.pk}/{seed}/{timezone.localdate()}")
    groups = defaultdict(list)
    ordinary = []
    auto = [c for c in configs if c.get("automatic") and any(c.get("weights",{"default":1}).values())]
    known = {v for c in auto for v in c.get("known_sounds",[])}
    for candidate in candidates:
        base,key,strand,reason = candidate
        if auto and key == "blend-v1" and not permitted_blend(key,0,child.lesson_theme,known):
            continue
        if auto and key == "magic-e-v1" and not any(c.get("advanced_decoding") for c in auto):
            continue
        boost = lesson_weight(key,configs,child.lesson_theme)
        if auto and key=="blend-v1" and any(c.get("letters") and activity_weight(c,"blend") for c in auto):
            boost = max(1,boost)
        if boost:
            group = MIX.get(objectives(key)[0], "Other activities")
            groups[group].append((boost,candidate))
        else:
            ordinary.append(candidate)
    # Normalize the activity mix over eligible types. More lessons in a type must
    # not multiply its chance of getting the first pick. Within each type retain
    # the existing comfort, recency and performance ordering.
    ranked = []
    for members in groups.values():
        weight = max(w for w,_ in members)
        clock = 0.0
        for _, (base,key,strand,_) in sorted(members,key=lambda entry:entry[1][0]+rng.random()*.4,reverse=True):
            clock -= log(1-rng.random())/weight
            ranked.append((clock,key,strand))
    ranked.sort()
    ceiling = max((base for base,_,_,_ in candidates),default=0)+len(ranked)+1
    return ordinary+[(ceiling-i,key,strand,"Practice focus") for i,(_,key,strand) in enumerate(ranked)]
