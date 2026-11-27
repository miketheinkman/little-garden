import json
import random

from django.db import transaction
from django.db.models import F, Max

from .focus import compile_round, policy_for
from .models import Learner, Purpose
from .practice import CURRENT_VERSION, FIVE_PROMPT_ROUNDS, LESSONS, build_round, round_count
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


def session_purpose(child, key, purpose):
    if purpose == Purpose.PRACTICE and LESSONS[key].get("checkin"):
        previous = child.assignment_set.filter(lesson=key, completed__isnull=False, skipped=0, step__gt=0,
                                               samples__isnull=False).exists()
        return Purpose.REVIEW if previous else Purpose.PLACEMENT
    return purpose


@transaction.atomic
def assign_lesson(child, key, variation=None, letters=None, *, purpose=Purpose.PRACTICE, policy=None):
    Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
    purpose = session_purpose(child, key, purpose)
    if variation is None:
        variation = next_round(child, key)
    last = child.assignment_set.aggregate(last=Max("position"))["last"] or 0
    if policy is None:
        policy = policy_for(child, key, purpose)
    snapshot = compile_round(key, variation, letters, policy)
    if policy and "_opened_theme" not in snapshot:
        snapshot = dict(snapshot, _opened_theme=policy["theme"])
    return child.assignment_set.create(lesson=key, purpose=purpose, position=last+1, variation=variation,
                                round_snapshot=snapshot)


def active_lesson_keys(child):
    keys = child.assignment_set.filter(completed=None, removed_at=None).values_list("lesson", flat=True)
    return {CURRENT_VERSION.get(key, key) for key in keys}


@transaction.atomic
def queue_available(child, keys, variation=None, letters=None, *, purpose=Purpose.PRACTICE, policy=None):
    # Serialize single and bulk adds before reading the queue, including on SQLite.
    Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
    active = active_lesson_keys(child)
    added = []
    for key in keys:
        current = CURRENT_VERSION.get(key, key)
        if current not in active:
            assign_lesson(child, key, variation, letters, purpose=purpose, policy=policy)
            active.add(current)
            added.append(key)
    return added, active
