"""Release plans by local calendar date when a family visits the queue."""
from datetime import date, timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .assignments import assign_lesson
from .models import Learner, LessonPlan


def occurrence(plan, day, direction=1):
    if plan.repeat == LessonPlan.Repeat.WEEKDAYS:
        allowed = "01234"
    elif plan.repeat == LessonPlan.Repeat.WEEKLY:
        allowed = plan.weekdays
    else:
        allowed = "0123456"
    for offset in range(7):
        ordinal = day.toordinal() + offset * direction
        if not 1 <= ordinal <= date.max.toordinal():
            return None
        candidate = date.fromordinal(ordinal)
        if str(candidate.weekday()) in allowed:
            return candidate if not plan.ends_on or candidate <= plan.ends_on else None
    return None


def release_due(child, today=None):
    today = today or timezone.localdate()
    due = child.lessonplan_set.filter(next_on__lte=today).order_by("next_on", "pk")
    if not due.exists():
        return
    with transaction.atomic():
        # The queue and the plan cursor move together, even with two devices visiting.
        Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
        for plan in due:
            day = plan.next_on
            following = None
            if plan.repeat != LessonPlan.Repeat.ONCE:
                day = occurrence(plan, min(today, plan.ends_on or today), direction=-1)
                if today < date.max:
                    following = occurrence(plan, today + timedelta(days=1))
            if plan.repeat == LessonPlan.Repeat.ONCE or not plan.assignment_set.filter(completed=None, removed_at=None).exists():
                row = assign_lesson(child, plan.lesson, plan.first_variation, plan.letters)
                row.plan = plan
                row.scheduled_for = day
                row.save(update_fields=["plan", "scheduled_for"])
                plan.first_variation = None
            plan.next_on = following
            plan.save(update_fields=["next_on", "first_variation"])
