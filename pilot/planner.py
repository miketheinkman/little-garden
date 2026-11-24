import uuid
from collections import defaultdict
from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .discovery import PATCH, letter_selection
from .models import Learner, LessonPlan
from .practice import CURRENT_LESSONS, LESSONS, round_count
from .scheduling import occurrence, release_due
from .themes import summary

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class PlanForm(forms.Form):
    lesson = forms.ChoiceField(label="Lesson")
    start = forms.DateField(label="First available", widget=forms.DateInput(attrs={"type": "date"}))
    repeat = forms.ChoiceField(label="Repeat", choices=LessonPlan.Repeat.choices)
    weekdays = forms.MultipleChoiceField(label="Practice days", required=False, widget=forms.CheckboxSelectMultiple,
                                         choices=[(str(i), d) for i, d in enumerate(DAYS)])
    end = forms.DateField(label="Last day (optional)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    submission = forms.UUIDField(widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        start, end, repeat = data.get("start"), data.get("end"), data.get("repeat")
        if not start or not repeat:
            return data
        if start < timezone.localdate():
            self.add_error("start", "Choose today or a future date.")
        if repeat == "weekly" and not data.get("weekdays"):
            self.add_error("weekdays", "Choose at least one practice day.")
            return data
        if repeat != "weekly":
            data["weekdays"] = []
        if repeat == "once":
            end = data["end"] = None
        plan = LessonPlan(repeat=repeat, weekdays="".join(data["weekdays"]), ends_on=end)
        data["next_on"] = occurrence(plan, start)
        if not data["next_on"]:
            self.add_error("end", "Choose a last day that includes at least one practice date.")
        return data


@login_required
@require_http_methods(["GET", "POST"])
def planner(request, pk):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    today = timezone.localdate()
    release_due(child, today)
    upcoming = child.lessonplan_set.filter(next_on__isnull=False)
    editing = get_object_or_404(upcoming, pk=request.GET["edit"]) if request.GET.get("edit", "").isdecimal() else None
    if "edit" in request.GET and not editing:
        raise Http404
    key = editing.lesson if editing else request.GET.get("lesson")
    if key and key not in LESSONS:
        raise Http404
    variation = editing.first_variation if editing else None
    letters = editing.letters if editing else ""
    if not editing and "v" in request.GET:
        try:
            variation = int(request.GET["v"])
            if not key or not 0 <= variation < round_count(key):
                raise ValueError
            if key == PATCH and request.GET.get("letters"):
                letters = letter_selection(request.GET["letters"])
        except ValueError:
            raise Http404
    try:
        selected = date.fromisoformat(request.GET["day"]) if "day" in request.GET else None
    except ValueError:
        raise Http404
    initial = {"lesson": key, "start": editing.next_on if editing else max(today, selected or today + timedelta(days=1)),
               "repeat": editing.repeat if editing else "once", "weekdays": list(editing.weekdays) if editing else [],
               "end": editing.ends_on if editing else None, "submission": editing.submission if editing else uuid.uuid4()}
    form = PlanForm(request.POST if request.method == "POST" else None, initial=initial, label_suffix="")
    groups = defaultdict(list)
    for lesson_key in ([key] if key else CURRENT_LESSONS):
        info = summary(lesson_key, LESSONS[lesson_key], child.lesson_theme)
        groups[info["category"]].append((lesson_key, info["title"]))
    form.fields["lesson"].choices = list(sorted(groups.items())) if key else [("", "Choose a lesson"), *sorted(groups.items())]
    form.fields["start"].widget.attrs["min"] = today.isoformat()
    if request.method == "POST" and request.POST.get("action") == "cancel":
        if not request.POST.get("plan", "").isdecimal():
            raise Http404
        with transaction.atomic():
            Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
            get_object_or_404(child.lessonplan_set, pk=request.POST["plan"])
            upcoming.filter(pk=request.POST["plan"]).update(next_on=None)
        messages.success(request, "Canceled the upcoming lesson dates.")
        return redirect("planner", pk=pk)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        values = dict(lesson=data["lesson"], next_on=data["next_on"], repeat=data["repeat"],
                      weekdays="".join(data["weekdays"]), ends_on=data["end"])
        with transaction.atomic():
            Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
            if editing:
                if not upcoming.filter(pk=editing.pk).update(**values):
                    raise Http404
            else:
                child.lessonplan_set.get_or_create(submission=data["submission"], defaults={
                    **values, "first_variation": variation, "letters": letters})
            release_due(child, today)
        messages.success(request, "Updated the lesson schedule." if editing else "Lesson scheduled.")
        return redirect(reverse("planner", args=[pk]) + "?day=" + data["start"].isoformat())
    plans = list(upcoming.order_by("next_on", "pk"))
    for plan in plans:
        plan.title = summary(plan.lesson, LESSONS[plan.lesson], child.lesson_theme)["title"]
        plan.cadence = ", ".join(DAYS[int(d)][:3] for d in plan.weekdays) if plan.repeat == "weekly" else plan.get_repeat_display()
    # Show successive sessions so families can see how plans fit together.
    anchor = max(today, selected or (editing.next_on if editing else today))
    week_start = anchor - timedelta(days=anchor.weekday())
    visible = min(7, date.max.toordinal() - week_start.toordinal() + 1)
    week_end = week_start + timedelta(days=visible - 1)
    assigned = defaultdict(list)
    for row in child.assignment_set.filter(scheduled_for__range=(week_start, week_end), removed_at=None):
        title = summary(row.lesson, LESSONS[row.lesson], child.lesson_theme)["title"]
        assigned[row.scheduled_for].append(f"{title} ({'completed' if row.completed else 'in queue'})")
    agenda = []
    for offset in range(visible):
        day = week_start + timedelta(days=offset)
        lessons = assigned[day] + [plan.title for plan in plans if day >= plan.next_on and
                  (day == plan.next_on or plan.repeat != "once" and occurrence(plan, day) == day)]
        if lessons:
            agenda.append((day, lessons))
    return render(request, "planner.html", {"child": child, "form": form, "plans": plans, "editing": editing, "agenda": agenda,
                                            "week_start": week_start, "week_end": week_end,
                                            "previous_week": week_start-timedelta(days=7) if week_start > today else None,
                                            "next_week": week_end+timedelta(days=1) if week_end < date.max else None,
                                            "variation": variation, "letters": letters, "zone": "Central" if timezone.get_current_timezone_name() == "America/Chicago" else timezone.get_current_timezone_name()})
