from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .models import Assignment, LessonFeedback
from .views import LESSONS


@never_cache
@login_required
def dashboard(request):
    if not (request.user.is_staff or request.user.has_perm("pilot.review_lessons")):
        raise PermissionDenied
    selected = request.GET.get("lesson", "")
    flag = request.GET.get("flag", "")
    lessons = {key: lesson for key, lesson in LESSONS.items() if not selected or selected == key}
    assignments = Assignment.objects.filter(lesson__in=lessons)
    notes = LessonFeedback.objects.filter(lesson__in=lessons)
    metrics = {
        row["lesson"]: row for row in assignments.order_by().values("lesson").annotate(
            assigned=Count("id"),
            started=Count("id", filter=Q(step__gt=0) | Q(retries__gt=0) | Q(completed__isnull=False)),
            finished=Count("id", filter=Q(completed__isnull=False)),
            learners=Count("learner_id", distinct=True, filter=Q(step__gt=0) | Q(retries__gt=0) | Q(completed__isnull=False)),
            retries=Sum("retries"),
        )
    }
    counts = {}
    for row in notes.order_by().values("lesson", "kind").annotate(total=Count("id")):
        counts.setdefault(row["lesson"], {})[row["kind"]] = row["total"]
    rows = []
    for key, lesson in lessons.items():
        data = metrics.get(key, {})
        flags = counts.get(key, {})
        rows.append({
            "key": key, "title": lesson["title"], "assigned": data.get("assigned", 0),
            "started": data.get("started", 0), "finished": data.get("finished", 0),
            "retries": data["retries"] if data.get("learners", 0) >= 5 else None,
            "worked": flags.get("worked", 0), "confusing": flags.get("confusing", 0),
            "change": flags.get("change", 0),
        })
    rows.sort(key=lambda row: (-(row["confusing"] + row["change"]), -row["started"], row["title"]))
    totals = {field: sum(row[field] for row in rows) for field in ("assigned", "started", "finished")}
    if flag:
        notes = notes.filter(kind=flag)
    page = Paginator(notes.values("lesson", "step", "kind", "note", "created"), 15).get_page(request.GET.get("page"))
    labels = dict(LessonFeedback.Kind.choices)
    for note in page:
        note["title"] = lessons[note["lesson"]]["title"]
        note["label"] = labels[note["kind"]]
    return render(request, "dashboard.html", {
        "lessons": LESSONS, "selected": selected, "flags": LessonFeedback.Kind.choices,
        "flag": flag, "rows": rows, "notes": page, "totals": totals,
    })
