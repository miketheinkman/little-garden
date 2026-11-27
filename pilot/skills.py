"""Curriculum objectives and the direct concepts a particular question actually tests."""
from collections import defaultdict
import re
from .remix import VOWELS, DIGRAPHS
from .practice import CURRENT_LESSONS
from .question_sets import identity

# Stable lesson stems also cover earlier versions of saved assignments.
CURRICULUM = {
    "Literacy": {
        "Alphabet": "case-match my-letters alphabet-gap letter-dots",
        "Letter formation": "letters lowercase",
        "Phonics": "sounds middle-sound digraphs blend magic-e animal-words",
        "Phonological awareness": "rhymes syllables",
        "Reading comprehension": "book snail story sentence",
    },
    "Math": {
        "Counting and numerals": "count1 count2 beans berry-basket number-dots digits hear-number more twos tens",
        "Arithmetic": "five ten market harvest add-groups take-away seesaw",
        "Money": "coins money-id money-total",
        "Measurement": "measure big-small tall-short clock",
        "Patterns and classification": "pattern sort-baskets",
        "Spatial relationships": "over-under left-right-pics inside-outside",
    },
    "Keyboard and mouse": {
        "Keyboard": "keys number-keys signs shift arrow-maze backspace",
        "Pointer control": "ladybugs lines river",
    },
    "Science": {
        "Investigation": "shadow sink-float weather living",
        "Animals": "animal-calls animal-lookout",
    },
    "Art and perception": {
        "Colors": "match-paint name-paint mix-paint color-baskets",
        "Visual discrimination": "same-different",
        "Drawing": "color draw mirror",
    },
    "Reasoning": {
        "Causality": "water-works train-tracks light-paths bridges delivery-routes gears-motion gates-switches",
        "Memory": "letter-memory picture-memory sound-memory",
        "Real and imaginary": "real-imaginary",
    },
    "Movement and music": {"Coordination": "left-right scissors", "Rhythm": "drums"},
    "Social studies": {"Calendar and culture": "holiday-clues holiday-traditions"},
}
PATHS = {stem: (subject, branch) for subject, branches in CURRICULUM.items()
         for branch, stems in branches.items() for stem in stems.split()}
PATHS.update({"copy-word": PATHS["signs"]})
CHECKS = {"number-check": ("count1", "five", "tens"), "key-check": ("keys", "copy-word", "signs"),
          "sound-check": ("sounds", "middle-sound", "digraphs")}
LABELS = {key.rsplit("-v", 1)[0]: lesson["skill"] for key, lesson in CURRENT_LESSONS.items()}
LABELS.update({"copy-word": "Copy a short word", "keys": "Find a letter key", "sounds": "Identify an initial sound"})
# Count a set is the same objective in both counting lessons.
ALIAS = {"count2": "count1"}
LETTER = set("case-match my-letters alphabet-gap letters lowercase keys shift animal-words".split())
SOUND = {"sounds", "middle-sound", "digraphs"}
NUMBER = set("number-keys count1 count2 digits berry-basket hear-number tens twos".split())
COLOR = {"match-paint", "name-paint", "mix-paint"}
OPERATORS = {"five": "Addition", "ten": "Addition", "market": "Addition", "add-groups": "Addition",
             "take-away": "Subtraction", "harvest": "Equal sharing"}
FACETS = {"phonemes": "Letter–sound link", "letters": "Letter", "sounds": "Sound spelling", "numbers": "Number", "operators": "Operator",
          "colors": "Color", "shapes": "Shape", "words": "Word", "relations": "Relationship",
          "times": "Time", "animals": "Animal", "money": "Denomination", "sequence": "Sequence"}

def objectives(key):
    stem = key.rsplit("-v", 1)[0]
    return CHECKS.get(stem, (ALIAS.get(stem, stem),))


# This bank is authored as short-vowel CVC examples. Extend with the regular
# words used by the original themed prompts. Unknown words get spelling evidence only.
SHORT_VOWELS = {**{w.lower():v for v,words in VOWELS.items() for w in words},
                "cab":"a","pad":"a","sap":"a","top":"o"}
VOWEL_SOUNDS = {"a":"æ","e":"ɛ","i":"ɪ","o":"ɑ","u":"ʌ"}
ONSET_SOUNDS = dict(zip("bcdfghjklmnprstvw yz".replace(" ",""),
                        ("b","k","d","f","ɡ","h","dʒ","k","l","m","n","p","ɹ","s","t","v","w","j","z"),strict=True))


def phoneme_link(obj,item,answer):
    quoted = re.search(r'“([A-Za-z]+)”',item["prompt"])
    word = (item.get("word") or (quoted[1] if quoted else "")).lower()
    spelling = answer.lower()
    sound = None
    if obj == "middle-sound" and SHORT_VOWELS.get(word) == spelling:
        sound = VOWEL_SOUNDS[spelling]
    elif obj == "sounds" and word in SHORT_VOWELS and word.startswith(spelling):
        sound = ONSET_SOUNDS.get(spelling)
    elif obj == "digraphs" and word in {w.lower() for w in DIGRAPHS.get(spelling,())}:
        sound = {"sh":"ʃ","ch":"tʃ","th":"θ"}[spelling]
    return f"{answer.upper()} · /{sound}/" if sound else None


def direct_target(key, item, step):
    options = objectives(key)
    objective = options[step] if len(options) > 1 else options[0]
    answer = str(item.get("answer", ""))
    facets = {}
    if objective in LETTER:
        facets["letters"] = [answer.upper()]
    elif objective == "blend" and len(answer) == 1:
        facets["sounds"] = [answer.upper()]
    elif objective in SOUND:
        facets["sounds"] = [answer.upper()]
        link = phoneme_link(objective,item,answer)
        if link:
            facets["phonemes"] = [link]
    elif objective in NUMBER:
        facets["numbers"] = [answer]
    elif objective in COLOR:
        facets["colors"] = [answer.lower()]
    elif objective in {"five", "ten"}:
        total = 5 if objective == "five" else 10
        facets["numbers"] = sorted({str(total), str(total-int(answer)), answer})
    elif objective in {"add-groups", "take-away"}:
        left, _, right = item["equation"].split()
        facets["numbers"] = list(dict.fromkeys((left, right)))
    elif objective == "market":
        operands, _ = identity("market",item,step)
        if operands:
            facets["numbers"] = list(dict.fromkeys(operands))
    elif objective in {"more", "harvest"}:
        facets["numbers"] = list(dict.fromkeys(map(str, item.get("piles", [item.get("carrots"), item.get("rabbits")]))))
    elif objective in {"rhymes", "syllables", "magic-e", "backspace", "copy-word", "signs"}:
        facets["words"] = [item.get("word") or answer]
    elif objective in {"left-right-pics", "over-under", "inside-outside", "big-small", "tall-short"}:
        facets["relations"] = [answer]
    elif objective in {"animal-lookout", "animal-calls"}:
        facets["animals"] = [answer]
    elif objective == "clock":
        facets["times"] = [answer]
    elif objective == "money-id":
        facets["money"] = [next((m["name"] for m in item["money"] if m["mark"] == answer),answer)]
    elif objective == "same-different" and item.get("target_shape"):
        facets["shapes"] = [item["target_shape"]]
    elif objective == "color-baskets":
        facets["colors"] = sorted({piece["color"] for piece in item["pieces"]})
    elif objective in {"letter-dots", "number-dots"}:
        facets["sequence"] = ["–".join([item["dots"][0]["label"], item["dots"][-1]["label"]])]
    if objective in OPERATORS:
        facets["operators"] = [OPERATORS[objective]]
    return {"objective": objective, "facets": facets}


def scored_evidence(child, purpose=None):
    from .models import SkillSample
    from .progression import OBSERVED_LESSONS
    rows = SkillSample.objects.filter(assignment__learner=child, puzzle_help=0).exclude(
        assignment__lesson__in=OBSERVED_LESSONS).select_related("assignment").order_by("measured","pk")
    if purpose:
        rows = rows.filter(assignment__purpose=purpose)
    for sample in rows.iterator(chunk_size=200):
        target = sample.direct
        if not target:
            row = sample.assignment
            from .themes import assignment_lesson
            if row.round_snapshot and "_opened_theme" in row.round_snapshot and 0 <= sample.step < len(row.round_snapshot["items"]):
                item = assignment_lesson(row, child.lesson_theme)["items"][sample.step]
                target = direct_target(row.lesson, item, sample.step)
            else:
                # Historical rows without frozen questions can support only the coarse objective.
                options = objectives(row.lesson)
                if len(options) > 1 and sample.step >= len(options):
                    continue
                target = {"objective": options[sample.step] if len(options)>1 else options[0], "facets": {}}
        yield sample, target


def proficiency(values):
    if not values:
        return "Not checked yet"
    values = values[-6:]
    if len({v[1] for v in values}) < 2:
        return "Early evidence"
    return "Demonstrated" if sum(v[0] for v in values)/len(values) >= 80 else "Developing"


def known_targets(child):
    grouped = defaultdict(list)
    for sample, target in scored_evidence(child):
        for facet, values in target["facets"].items():
            for value in values:
                grouped[target["objective"], facet, value].append((sample.score, sample.assignment_id))
    return {key for key, values in grouped.items() if proficiency(values) == "Demonstrated"}

def round_change(points):
    """Compare the last two sessions with evidence for this exact skill or target."""
    sessions = defaultdict(list)
    for point in points:
        sessions[point[1]].append(point[0])
    if len(sessions) < 2:
        return ""
    newest = list(dict.fromkeys(p[1] for p in reversed(points)))[:2]
    current, previous = (sessions[k] for k in newest)
    difference = round(sum(current)/len(current) - sum(previous)/len(previous))
    return f"{difference:+d} points since the previous round"
