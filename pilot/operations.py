"""Aggregate pilot usage and a read-only snapshot of the host."""
from datetime import datetime, time as day_time, timedelta
from pathlib import Path
import shutil
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Assignment, Learner, SkillSample


def cpu_ticks():
    with Path("/proc/stat").open() as source:
        name, *values = source.readline().split()
    if name != "cpu" or len(values) < 4:
        raise ValueError("CPU totals unavailable")
    # The guest counters are already included in user and nice.
    ticks = [int(field) for field in values[:8]]
    return sum(ticks), sum(ticks[3:5])


def server_health():
    cpu = memory = disk = uptime = None
    try:
        total_before, idle_before = cpu_ticks()
        time.sleep(0.15)
        total, idle = cpu_ticks()
        elapsed = total - total_before
        if elapsed > 0:
            cpu = round(100 * max(0, min(1, 1 - (idle - idle_before) / elapsed)))
    except (OSError, ValueError):
        pass
    try:
        fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        total = int(fields["MemTotal"].split()[0]) * 1024
        available = int(fields["MemAvailable"].split()[0]) * 1024
        if 0 <= available <= total and total:
            memory = {"used": total - available, "total": total, "percent": round(100 * (total - available) / total)}
    except (KeyError, IndexError, OSError, ValueError):
        pass
    try:
        usage = shutil.disk_usage(settings.BASE_DIR)
        disk = {"free": usage.free, "total": usage.total}
    except OSError:
        pass
    try:
        hours = int(float(Path("/proc/uptime").read_text().split()[0])) // 3600
        uptime = f"{hours // 24}d {hours % 24}h" if hours else "Under 1h"
    except (OSError, ValueError, IndexError):
        pass
    return {"cpu": cpu, "memory": memory, "disk": disk, "uptime": uptime}


def pilot_usage(now):
    today = timezone.localdate(now)
    first_day = today - timedelta(days=29)
    start = timezone.make_aware(datetime.combine(first_day, day_time.min))
    rounds = Assignment.objects.filter(completed__isnull=False, removed_at=None)
    recent = rounds.filter(completed__range=(start, now))
    # One family-day even if siblings play together or a round also has scored answers.
    finishes = recent.order_by().annotate(day=TruncDate("completed")).values_list("learner__parent_id", "day")
    practice = SkillSample.objects.filter(measured__range=(start, now)).order_by().annotate(
        day=TruncDate("measured")).values_list("assignment__learner__parent_id", "day")
    family_days = {}
    for parent_id, day in finishes.union(practice):
        family_days[parent_id] = family_days.get(parent_id, 0) + 1

    completed = recent.filter(skipped=0).order_by().annotate(day=TruncDate("completed"))
    daily = dict(completed.values("day").annotate(total=Count("pk")).values_list("day", "total"))
    week = [(date, daily.get(date, 0)) for date in (today - timedelta(days=i) for i in range(6, -1, -1))]
    peak = max(count for day, count in week) or 1
    return {
        "accounts": get_user_model().objects.aggregate(
            registered=Count("pk"), new=Count("pk", filter=Q(date_joined__range=(start, now)))),
        "learners": Learner.objects.count(),
        "sessions": Session.objects.filter(expire_date__gt=now).count(),
        "active": len(family_days), "returning": sum(days >= 2 for days in family_days.values()),
        "totals": rounds.aggregate(completed=Count("pk", filter=Q(skipped=0)), with_skips=Count("pk", filter=Q(skipped__gt=0))),
        "week": [(day, count, round(100 * count / peak)) for day, count in week],
        "week_total": sum(count for day, count in week),
    }
