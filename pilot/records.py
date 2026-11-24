"""Family observations and a printable, local-calendar learning record."""
from datetime import date, timedelta
import uuid

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import Learner, SkillSample
from .themes import assignment_lesson


class ObservationForm(forms.Form):
    observed_on = forms.DateField(label="Date observed", widget=forms.DateInput(attrs={"type":"date"}))
    text = forms.CharField(label="What did you notice?", max_length=2000, widget=forms.Textarea(attrs={"rows":3}))
    submission = forms.UUIDField(widget=forms.HiddenInput)

    def clean_observed_on(self):
        day = self.cleaned_data["observed_on"]
        if day > timezone.localdate():
            raise forms.ValidationError("Choose today or an earlier observation date.")
        return day


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def weekly_record(request, pk):
    child = get_object_or_404(Learner, pk=pk, parent=request.user)
    today = timezone.localdate()
    try:
        day = date.fromisoformat(request.GET["week"]) if "week" in request.GET else today
    except ValueError:
        raise Http404
    start = day - timedelta(days=day.weekday())
    end = date.fromordinal(min(start.toordinal()+6, date.max.toordinal()))
    assignment = None
    editing = None
    if "assignment" in request.GET:
        assignment = get_object_or_404(child.assignment_set, pk=_id(request.GET["assignment"]))
    if "edit" in request.GET:
        editing = get_object_or_404(child.observation_set.select_related("assignment"), pk=_id(request.GET["edit"]))
        assignment = editing.assignment
    form = ObservationForm(request.POST if request.method == "POST" else None, label_suffix="", initial={
        "observed_on": editing.observed_on if editing else min(today, end),
        "text": editing.text if editing else "", "submission": editing.submission if editing else uuid.uuid4()})
    form.fields["observed_on"].widget.attrs["max"] = today.isoformat()
    url = reverse("weekly_record", args=[pk])
    if request.method == "POST":
        if request.POST.get("action") == "delete":
            note = get_object_or_404(child.observation_set, pk=_id(request.POST.get("note", "")))
            note.delete()
            messages.success(request, "Observation deleted.")
            return redirect(f"{url}?week={start.isoformat()}")
        if form.is_valid():
            data = form.cleaned_data
            values = dict(observed_on=data["observed_on"], text=data["text"], assignment=assignment)
            if editing:
                child.observation_set.filter(pk=editing.pk).update(**values)
            else:
                child.observation_set.get_or_create(submission=data["submission"], defaults=values)
            messages.success(request, "Observation saved.")
            return redirect(f"{url}?week={data['observed_on'].isoformat()}#observations")
    rows = list(child.assignment_set.filter(completed__date__range=(start,end)).order_by("completed", "pk"))
    for row in rows:
        row.info = assignment_lesson(row)
    notes = list(child.observation_set.filter(observed_on__range=(start,end)).select_related("assignment"))
    for note in notes:
        note.lesson_title = assignment_lesson(note.assignment)["title"] if note.assignment else ""
    independent = Q(puzzle_help=0)
    skills = (SkillSample.objects.filter(assignment__learner=child, measured__date__range=(start, end))
              .values("strand").annotate(independent=Count("pk", filter=independent),
                                         average=Avg("score", filter=independent),
                                         assisted=Count("pk", filter=Q(puzzle_help__gt=0)))
              .order_by("strand"))
    return render(request, "weekly_record.html", dict(child=child, start=start, end=end, rows=rows, notes=notes, skills=skills,
        answered=sum(r.answered for r in rows), skipped=sum(r.skipped for r in rows), editing=editing, form=form,
        previous=start-timedelta(days=1) if start > date.min else None,
        following=end+timedelta(days=1) if end < today else None,
        assignment_title=assignment_lesson(assignment)["title"] if assignment else ""))


def _id(value):
    if not value.isascii() or not value.isdecimal() or len(value) > 18:
        raise Http404
    return int(value)
