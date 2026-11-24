import json
import random

from django.db import transaction
from django.db.models import F, Max

from .discovery import PATCH, discovery_round
from .models import Learner
from .practice import FIVE_PROMPT_ROUNDS, build_round, round_count
from .themes import themed_round


def question_set(child, key, variation):
    round_data = themed_round(key, build_round(key, variation), child.lesson_theme, variation)
    signatures = set()
    for item in round_data["items"]:
        if item.get("deck"):
            # Rotating the locations of the cards still practices the same pairs.
            core = sorted((c["label"], c.get("symbol", ""), c.get("clip", "")) for c in item["deck"])
        elif round_data["kind"] in {"key", "type"} or item.get("word"):
            core = (item.get("word", ""), item["answer"])
        else:
            ignored = {"choices", "letters", "tiles", "pictures", "animals", "bank_context"}
            core = {k: v for k, v in item.items() if k not in ignored}
        signatures.add(json.dumps(core, sort_keys=True, ensure_ascii=False))
    return signatures


def suggested_round(child, key, history):
    if not history:
        return 0
    count = round_count(key)
    # Consider all previous IDs until the pool is exhausted, then recycle oldest IDs first.
    last_used = {number: index for index, number in enumerate(history)}
    candidates = [number for number in range(count) if number not in last_used]
    if not candidates:
        candidates = sorted(last_used, key=last_used.get)[:max(1, count//2)]
    rng = random.Random(f"{child.pk}/{key}/{len(history)}/{history[-1]}")
    candidates = rng.sample(candidates, min(12, len(candidates)))
    previous = [question_set(child, key, n) for n in history[-3:]]
    def overlap(number):
        questions = question_set(child, key, number)
        return (questions == previous[-1], sum(len(questions & recent) for recent in previous))
    return min(candidates, key=overlap)


def next_round(child, key):
    versions = [key, key.replace("-v2", "-v1")] if key in FIVE_PROMPT_ROUNDS else [key]
    history = list(child.assignment_set.filter(lesson__in=versions).order_by("pk").values_list("variation", flat=True))
    return suggested_round(child, key, history)


@transaction.atomic
def assign_lesson(child, key, variation=None, letters=None):
    Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
    if variation is None:
        variation = next_round(child, key)
    last = child.assignment_set.aggregate(last=Max("position"))["last"] or 0
    return child.assignment_set.create(lesson=key, position=last+1, variation=variation,
                                round_snapshot=discovery_round(key, variation, letters) if key == PATCH and letters else build_round(key, variation))
