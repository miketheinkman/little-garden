"""Lesson-level assessment coverage for one family learner."""
from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .assignments import queue_available
from .assessment import METHODS, evidence_method, observation_prompt
from .models import Learner, Observation, Purpose
from .practice import CURRENT_LESSONS, CURRENT_VERSION
from .scheduling import release_due
from .themes import summary


def coverage(child, *, only_checkins=False):
    independent = Q(samples__puzzle_help=0)
    notes = Observation.objects.filter(learner=child, assignment_id=OuterRef("pk"))
    completed = (child.assignment_set.filter(completed__isnull=False, removed_at=None)
                 .annotate(scored=Count("samples", filter=independent), average=Avg("samples__score", filter=independent),
                           noted=Exists(notes))
                 .values("pk", "lesson", "purpose", "step", "skipped", "completed", "scored", "average", "noted")
                 .order_by("completed", "pk"))
    latest, baseline, practice, dates = {}, {}, {}, defaultdict(list)
    for row in completed:
        key = CURRENT_VERSION.get(row["lesson"], row["lesson"])
        lesson = CURRENT_LESSONS[key]
        observed = evidence_method(lesson) == "observation"
        full = row["step"] > 0 and not row["skipped"]
        if full and row["scored"] == row["step"] and not observed:
            dates[lesson["strand"]].append(row["completed"])
        if row["purpose"] == Purpose.PRACTICE and not lesson.get("checkin"):
            practice[key] = row["completed"]
            continue
        latest[key] = row
        if full and (row["noted"] if observed else row["scored"] == row["step"]):
            baseline[key] = row

    queued = {}
    for key, purpose in child.assignment_set.filter(removed_at=None, completed=None).values_list("lesson", "purpose"):
        queued.setdefault(CURRENT_VERSION.get(key, key), []).append(purpose)
    planned = defaultdict(list)
    for plan in child.lessonplan_set.filter(next_on__isnull=False).order_by("next_on", "pk"):
        key = CURRENT_VERSION.get(plan.lesson, plan.lesson)
        if plan.purpose != Purpose.PRACTICE or CURRENT_LESSONS[key].get("checkin"):
            planned[key].append(plan)

    strands = defaultdict(list)
    today = timezone.localdate()
    for key, lesson in CURRENT_LESSONS.items():
        if only_checkins and not lesson.get("checkin"):
            continue
        method = evidence_method(lesson)
        last = baseline.get(key)
        due = None
        if last:
            due = timezone.localdate(last["completed"]) + timedelta(weeks=4)
            rounds = dates[lesson["strand"]]
            eighth = bisect_right(rounds, last["completed"]) + 7
            if method != "observation" and eighth < len(rounds):
                due = min(due, timezone.localdate(rounds[eighth]))
        latest_check = latest.get(key)
        row = dict(key=key, title=summary(key, lesson, child.lesson_theme)["title"], level=lesson["level"],
                   skill=lesson["skill"], mode=lesson["participation"], method=METHODS[method],
                   observe=method == "observation", tip=observation_prompt(lesson) if method == "observation" else "", broad=lesson.get("checkin", False), last=last,
                   latest=latest_check, practice=practice.get(key), due=due,
                   queue=[Purpose(p).label for p in queued.get(key, [])], plans=planned[key],
                   placement_planned=any(p.purpose == Purpose.PLACEMENT for p in planned[key]),
                   review_planned=any(p.purpose == Purpose.REVIEW or p.repeat != "once" for p in planned[key]))
        if latest_check and latest_check != last:
            row["partial"] = True
        row["status"] = "Review due" if due and due <= today else "Checked" if last else "Awaiting baseline"
        row["next_date"] = max(today, due) if due else today + timedelta(weeks=4)
        strands[lesson["strand"]].append(row)
    groups = []
    for strand, rows in sorted(strands.items()):
        rows.sort(key=lambda r: (not r["broad"], r["observe"], r["level"], r["title"]))
        groups.append(dict(strand=strand, rows=rows, covered=sum(bool(r["last"]) for r in rows)))
    return groups


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def placement_reviews(request, pk):
    child = get_object_or_404(Learner, pk=pk, parent=request.user)
    release_due(child)
    if request.method == "POST":
        key, purpose = request.POST.get("lesson"), request.POST.get("purpose")
        if key not in CURRENT_LESSONS or purpose not in {Purpose.PLACEMENT, Purpose.REVIEW}:
            raise Http404
        added, _ = queue_available(child, [key], purpose=purpose)
        messages.success(request, f"{Purpose(purpose).label} added to the queue." if added else "This lesson is already queued.")
        filters = request.GET.copy()
        filters["open"] = key
        return redirect(f"{reverse('placement_reviews', args=[pk])}?{filters.urlencode()}#review-{key}")
    groups = coverage(child)
    strands = [group["strand"] for group in groups]
    selected = request.GET.get("strand", "")
    if selected and selected not in strands:
        raise Http404
    status = request.GET.get("status", "")
    statuses = ("Awaiting baseline", "Review due", "Checked")
    if status and status not in statuses:
        raise Http404
    visible = []
    for group in groups:
        if selected and group["strand"] != selected:
            continue
        rows = [r for r in group["rows"] if not status or r["status"] == status]
        if rows:
            visible.append(dict(**group, visible=rows))
    opened = CURRENT_LESSONS.get(request.GET.get("open"), {}).get("strand")
    return render(request, "placement_reviews.html", dict(opened=opened,
        child=child, groups=visible, strands=strands, strand=selected, statuses=statuses, status=status,
        checked=sum(g["covered"] for g in groups), total=len(CURRENT_LESSONS),
        due_count=sum(r["status"] == "Review due" for g in groups for r in g["rows"])))
