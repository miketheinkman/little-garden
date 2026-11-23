"""Local practice estimates. A level is a curriculum tier within one strand."""
from collections import defaultdict
from datetime import timedelta
from math import exp
from statistics import median

from django.utils import timezone

from .themes import summary
from .models import SkillSample
from .practice import CURRENT_LESSONS, CURRENT_VERSION, LESSONS


def fit(samples):
    """Fit recent observations to an ordered difficulty scale with a mild prior."""
    recent = samples[-24:]
    if not recent:
        return None
    # A provisional fluency signal needs repeated timed successes. Keep raw accuracy intact.
    timed = [s["ms_per_key"] for s in recent if s.get("ms_per_key") and s["score"] == 100]
    pace = median(timed) if len(timed) >= 3 else None
    def loss(ability):
        penalty = 0.025 * (ability - 1.5)**2
        for age, sample in enumerate(reversed(recent)):
            expected = 1 / (1 + exp(1.65 * (sample["level"] - ability) - 1))
            target = sample["score"]/100
            if pace and sample.get("ms_per_key") and target == 1:
                target -= .20 * min(1, max(0, (pace-5000)/55000))
            penalty += .94**age * (expected - target)**2
        return penalty
    ceiling = min(5, max(s["level"] for s in recent) + 1)
    return min((i/4 for i in range(4, 4*ceiling+1)), key=loss)


FIT_LABELS = ("On level", "Slightly above level", "Above level", "Slightly below level",
              "Below level", "Placement pending", "Placement check-in")


def record_tier(sample, child_id):
    """Carry the high-water mark forward once per new scored observation."""
    earlier = SkillSample.objects.filter(assignment__learner_id=child_id, strand=sample.strand,
                                         pk__lt=sample.pk, puzzle_help=0).order_by("-measured", "-pk")
    fields = ("level", "score", "ms_per_key", "peak_tier")
    previous = list(reversed(list(earlier.values(*fields)[:23])))
    peak = previous[-1]["peak_tier"] if previous else None
    if previous and peak is None:
        # Older installations have scores but no recorded milestones.
        from collections import deque
        window = deque(maxlen=24)
        peak = 1
        for observation in earlier.order_by("measured", "pk").values(*fields).iterator():
            window.append(observation)
            peak = max(peak, int(fit(list(window))))
    tier = int(fit([*previous, {"level": sample.level, "score": sample.score, "ms_per_key": sample.ms_per_key}]))
    sample.peak_tier = max(tier, peak or 1)
    sample.save(update_fields=["peak_tier"])
    if peak is not None and tier > peak:
        return {"strand": sample.strand, "tier": tier}


def band(level, estimate):
    if estimate is None:
        return "Placement pending"
    gap = level-estimate
    if abs(gap) <= .4:
        return "On level"
    if abs(gap) <= 1:
        return "Slightly above level" if gap > 0 else "Slightly below level"
    return "Above level" if gap > 0 else "Below level"


def item_score(kind, artwork):
    if kind in {"choice", "key", "type", "basket", "balance"}:
        return 100
    if kind in {"color", "mirror"} and artwork:
        from .art import match_score
        return match_score(kind, artwork["mask"], artwork["pixels"])
    return None


class Progress:
    def __init__(self, child):
        self.theme = child.lesson_theme
        self.samples = defaultdict(list)
        self.attempted = defaultdict(list)
        self.sessions = {}
        evidence = SkillSample.objects.filter(assignment__learner=child).order_by("measured", "pk").values(
            "assignment_id", "assignment__lesson", "strand", "level", "score", "measured", "ms_per_key", "puzzle_help")
        for s in evidence:
            if not s["puzzle_help"]:
                self.samples[s["strand"]].append(s)
            self.sessions.setdefault(s["assignment_id"], []).append(s)
        completed = child.assignment_set.exclude(completed=None).filter(skipped=0).order_by("-completed","-pk").values_list("pk", "lesson", "completed", "step")
        self.recent = []
        self.completed_steps = {}
        for pk, key, when, steps in completed:
            self.completed_steps[pk] = steps
            key = CURRENT_VERSION.get(key, key)
            self.attempted[key].append(when)
            self.recent.append(key)
        self.estimates = {strand: fit(samples) for strand, samples in self.samples.items()}

    def label(self, lesson):
        if lesson.get("checkin"):
            return "Placement check-in"
        return band(lesson["level"], self.estimates.get(lesson["strand"]))

    def timeline(self):
        history = []
        prior = {}
        for samples in self.sessions.values():
            first = samples[0]
            key = first["assignment__lesson"]
            levels = tuple(s["level"] for s in sorted(samples, key=lambda s: s["level"]))
            score = round(sum(s["score"] for s in samples)/len(samples))
            comparable = (key, levels)
            change = None if comparable not in prior else score-prior[comparable]
            prior[comparable] = score
            times = [s["ms_per_key"] for s in samples if s["ms_per_key"]]
            help_counts = None
            if LESSONS[key]["kind"] == "puzzle":
                help_counts = [sum(s["puzzle_help"] == value for s in samples) for value in range(4)]
            history.append(dict(help_counts=help_counts, seconds=round(median(times)/1000,1) if times else None, title=LESSONS[key]["title"], date=samples[-1]["measured"], strand=first["strand"],
                                levels=", ".join(map(str, sorted(set(levels)))), score=score,
                                count=len(samples), change=change))
        return sorted(history, key=lambda point: point["date"], reverse=True)

    def charts(self):
        charts = []
        for strand, samples in sorted(self.samples.items()):
            # Use the last observation of each round as a checkpoint. Keep the
            # underlying evidence chronological even when a child resumes an older round.
            last_index = {sample["assignment_id"]: i for i, sample in enumerate(samples)}
            indices = sorted(last_index.values())[-12:]
            points = []
            for pos, i in enumerate(indices):
                level = fit(samples[max(0, i-23):i+1])
                points.append({
                    "x": 30 + round(265 * pos / max(1, len(indices)-1)),
                    "y": 100 - round((level-1)*20), "level": level,
                    "date": samples[i]["measured"],
                })
            charts.append({
                "strand": strand, "points": points, "current": points[-1]["level"],
                "coordinates": " ".join(f'{point["x"]},{point["y"]}' for point in points),
                "first": points[0]["date"], "last": points[-1]["date"],
                "count": len(samples), "rounds": len(last_index),
            })
        return charts

    def recommendations(self):
        candidates = []
        # Give fluent rounds a rest, even when there is no harder lesson in that strand yet.
        by_lesson = defaultdict(list)
        for samples in self.sessions.values():
            key = samples[0]["assignment__lesson"]
            by_lesson[CURRENT_VERSION.get(key, key)].append(samples)
        review_cutoff = timezone.now() - timedelta(days=14)
        for key, lesson in CURRENT_LESSONS.items():
            if lesson.get("checkin") or lesson["participation"] != "Independent":
                continue
            strand, level = lesson["strand"], lesson["level"]
            estimate = self.estimates.get(strand)
            gap = level-(estimate if estimate is not None else 1)
            if gap < -1 or gap > 1:
                continue
            recent_rounds = by_lesson[key][-2:]
            if len(recent_rounds) == 2 and all(
                len(session) == self.completed_steps.get(session[0]["assignment_id"]) and all(s["score"] >= 90 and not s["puzzle_help"] for s in session)
                and session[-1]["measured"] > review_cutoff for session in recent_rounds
            ):
                continue
            data = self.samples.get(strand, [])[-6:]
            need = 1-sum(s["score"] for s in data)/(100*len(data)) if data else .25
            # Prefer a comfortable task or small stretch. Rotate away from recent successes.
            weight = 3*need - abs(gap-.25) - .6*self.recent[:4].count(key)
            if not self.attempted[key]:
                weight += .3
            if data and gap < -.4 and need < .25:
                continue
            reason = ("Practice after recent difficulty" if data and need >= .35 else
                      "A small stretch" if estimate is not None and gap > .4 else
                      "A starting activity" if estimate is None else "Practice near the current level")
            candidates.append((weight,key,strand,reason))
        result = []
        used = defaultdict(int)
        while candidates and len(result)<3:
            chosen = max(candidates,key=lambda c:c[0]-.95*used[c[2]])
            candidates.remove(chosen)
            _,key,strand,reason = chosen
            if used[strand] >= 2:
                continue
            used[strand] += 1
            result.append(dict(key=key,title=summary(key, LESSONS[key], self.theme)["title"],reason=reason,band=self.label(LESSONS[key])))
        return result

    def checkins(self):
        result = []
        for key, lesson in CURRENT_LESSONS.items():
            if not lesson.get("checkin"):
                continue
            recent = self.attempted[key]
            samples = self.samples.get(lesson["strand"], [])
            if not recent:
                reason = "Initial placement" if not samples else "Check current placement"
            elif recent[0] < timezone.now()-timedelta(days=28) or len({s["assignment_id"] for s in samples if s["measured"]>recent[0]})>=8:
                reason = "Recheck suggested"
            else:
                reason = "Available to repeat"
            result.append(dict(key=key,title=lesson["title"],reason=reason))
        return result
