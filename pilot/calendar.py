"""Family calendar and the weekly planner share one projection of scheduled work."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import Assignment, Learner, LessonPlan, Purpose
from .practice import LESSONS
from .scheduling import occurrence, release_due
from .themes import summary


def scheduled_entries(children, plans, start, end):
    """Show released work on its recorded date and project future plan dates."""
    entries = defaultdict(list)
    rows = (Assignment.objects.filter(learner__in=children, scheduled_for__range=(start, end), removed_at=None)
            .select_related("learner").order_by("learner__nickname", "position", "pk"))
    for row in rows:
        base = row.round_snapshot or LESSONS[row.lesson]
        theme = base.get("_opened_theme", row.learner.lesson_theme)
        title = summary(row.lesson, base, theme)["title"]
        entries[row.scheduled_for].append(dict(child=row.learner, title=title,
                                               purpose=row.get_purpose_display(), status="Completed" if row.completed else "In queue"))
    for plan in plans:
        if plan.next_on > end:
            continue
        if plan.repeat == LessonPlan.Repeat.ONCE:
            day = plan.next_on if start <= plan.next_on else None
        else:
            day = occurrence(plan, max(start, plan.next_on))
        title = summary(plan.lesson, LESSONS[plan.lesson], plan.learner.lesson_theme)["title"]
        while day and day <= end:
            purpose = Purpose.REVIEW if plan.purpose == Purpose.PLACEMENT and day > plan.next_on else plan.purpose
            entries[day].append(dict(child=plan.learner, title=title, status="Planned", purpose=Purpose(purpose).label, plan=plan))
            if day == end or plan.repeat == LessonPlan.Repeat.ONCE:
                break
            day = occurrence(plan, day + timedelta(days=1))
    return entries


@login_required
@never_cache
@require_safe
def family_calendar(request):
    today = timezone.localdate()
    try:
        selected = date.fromisoformat(request.GET["day"]) if "day" in request.GET else today
    except ValueError:
        raise Http404
    children = list(Learner.objects.filter(parent=request.user).order_by("nickname", "pk"))
    selected_child = None
    if request.GET.get("child"):
        selected_child = next((child for child in children if str(child.pk) == request.GET["child"]), None)
        if selected_child is None:
            raise Http404
    visible_children = [selected_child] if selected_child else children
    for child in visible_children:
        release_due(child, today)
    start = selected.replace(day=1)
    end = selected.replace(day=calendar.monthrange(selected.year, selected.month)[1])
    plans = (LessonPlan.objects.filter(learner__in=visible_children, next_on__lte=end)
             .select_related("learner").order_by("learner__nickname", "next_on", "pk"))
    entries = scheduled_entries(visible_children, plans, start, end)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(selected.year, selected.month):
        cells = []
        for number in week:
            day = start.replace(day=number) if number else None
            cells.append({"date": day, "entries": entries.get(day, [])} if day else None)
        weeks.append(cells)
    return render(request, "family_calendar.html", {
        "children": children, "selected_child": selected_child, "visible_children": visible_children,
        "today": today, "selected": selected, "weeks": weeks, "weekdays": calendar.day_name,
        "previous": (start - timedelta(days=1)).replace(day=1) if start > date.min else None,
        "following": end + timedelta(days=1) if end < date.max else None,
        "selected_entries": entries.get(selected, []), "month_count": sum(map(len, entries.values())),
    })
