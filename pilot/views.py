import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import F, Max
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Assignment, Learner

LESSONS = json.loads((settings.BASE_DIR / "content/lessons.json").read_text())


def signup(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.session.flush()
        login(request, form.save())
        return redirect("home")
    return render(request, "account.html", {"form": form, "title": "Create a parent account"})


def home(request):
    if request.user.is_authenticated:
        learners = list(Learner.objects.filter(parent=request.user))
        for child in learners:
            child.queue = decorate(child.assignment_set.filter(completed=None))
            child.record = decorate(child.assignment_set.filter(
                completed__gte=timezone.now()-timedelta(days=7)).order_by("-completed"))
        return render(request, "parent.html", {"learners": learners, "lessons": LESSONS})
    child = Learner.objects.filter(pk=request.session.get("child")).first()
    if child:
        return render(request, "child.html", {"child": child, "queue": decorate(
            child.assignment_set.filter(completed=None))})
    return redirect("login")


def decorate(rows):
    rows = list(rows)
    for row in rows:
        row.info = LESSONS[row.lesson]
    return rows


@login_required
@require_POST
def add_child(request):
    name = request.POST.get("nickname", "").strip()
    if not 0 < len(name) <= 40:
        return HttpResponseBadRequest("Enter a nickname up to 40 characters.")
    Learner.objects.create(parent=request.user, nickname=name)
    return redirect("home")


@login_required
@require_POST
def manage(request, pk):
    child = get_object_or_404(Learner, pk=pk, parent=request.user)
    action = request.POST.get("action")
    if action == "play":
        request.session.flush()
        request.session["child"] = child.pk
    elif action == "assign" and request.POST.get("lesson") in LESSONS:
        last = child.assignment_set.aggregate(last=Max("position"))["last"] or 0
        child.assignment_set.create(lesson=request.POST["lesson"], position=last+1)
    elif action == "first":
        row = get_object_or_404(child.assignment_set, pk=request.POST["row"], completed=None)
        first = child.assignment_set.filter(completed=None).first()
        row.position = first.position-1
        row.save(update_fields=["position"])
    else:
        return HttpResponseBadRequest("Unknown action.")
    return redirect("home")


def play(request, pk):
    if request.user.is_authenticated:
        return redirect("home")
    row = get_object_or_404(Assignment, pk=pk, learner_id=request.session.get("child"))
    if row.completed:
        return redirect("home")
    lesson = LESSONS[row.lesson]
    item = lesson["items"][row.step]
    error = ""
    if request.method == "POST":
        current = Assignment.objects.filter(pk=pk, step=row.step, completed=None)
        if request.POST.get("step") != str(row.step):
            return redirect("play", pk)
        if request.POST.get("answer", "").casefold() == item["answer"].casefold():
            done = row.step+1 == len(lesson["items"])
            updated = current.update(step=F("step")+1, completed=timezone.now() if done else None)
            if done and updated:
                messages.success(request, f"Finished {lesson['title']}! Well done.")
            return redirect("home") if done else redirect("play", pk)
        current.update(retries=F("retries")+1)
        error = "Take another look. You can try again."
    return render(request, "play.html", {"row": row,"lesson": lesson,"item": item,"error": error})
