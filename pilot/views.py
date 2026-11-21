from datetime import timedelta

from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import ParentSignupForm, RecoveryEmailForm
from django.db.models import F, Max
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from .models import Assignment, Learner, LessonFeedback, FeedbackEmailPreference

from .art import art_item, evaluate
from .practice import LESSONS, build_round, round_count


def lesson_response(request, lesson, item):
    if "shape" in item:
        pixels = request.POST.get("pixels", "")
        feedback = evaluate(lesson["kind"], item["mask"], pixels)
        if feedback is None:
            return False, None
        return True, {"pixels": pixels, "feedback": feedback, "mask": item["mask"], "kind": lesson["kind"]}
    return request.POST.get("answer", "").casefold() == item["answer"].casefold(), None


def signup(request):
    form = ParentSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.session.flush()
        login(request, form.save())
        return redirect("home")
    return render(request, "account.html", {"form": form, "heading": "Create a parent account"})


@login_required
def recovery_email(request):
    form = RecoveryEmailForm(request.POST or None, initial={"email": request.user.email})
    if request.method == "POST" and form.is_valid():
        if request.user.check_password(form.cleaned_data["password"]):
            request.user.email = form.cleaned_data["email"]
            request.user.save(update_fields=["email"])
            return redirect("home")
        form.add_error("password", "Check your current password and try again.")
    return render(request, "recovery.html", {
        "form": form, "heading": "Recovery email", "button": "Save email",
    })


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
        row.info = getattr(row, "round_snapshot", None) or LESSONS[row.lesson]
    return rows


@login_required
@require_POST
def add_child(request):
    name = request.POST.get("nickname", "").strip()
    if not 0 < len(name) <= 40:
        return HttpResponseBadRequest("Enter a nickname up to 40 characters.")
    Learner.objects.create(parent=request.user, nickname=name)
    return redirect("home")


def requested_round(key, value):
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise Http404
    if not 0 <= number < round_count(key):
        raise Http404
    return number


def next_round(child, key):
    last = child.assignment_set.filter(lesson=key).order_by("-pk").values_list("variation", flat=True).first()
    return 0 if last is None else (last+1) % round_count(key)


def assign_lesson(child, key, variation=None):
    if variation is None:
        variation = next_round(child, key)
    last = child.assignment_set.aggregate(last=Max("position"))["last"] or 0
    child.assignment_set.create(lesson=key, position=last+1, variation=variation,
                                round_snapshot=build_round(key, variation))


@login_required
@require_http_methods(["GET", "POST"])
def library(request, pk):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    if request.method == "POST":
        key = request.POST.get("lesson")
        if key not in LESSONS:
            return HttpResponseBadRequest("Choose a lesson from the library.")
        variation = requested_round(key, request.POST["variation"]) if "variation" in request.POST else None
        assign_lesson(child, key, variation)
        messages.success(request, f"{LESSONS[key]['title']} added to {child.nickname}’s queue.")
        return redirect(request.get_full_path())

    category = request.GET.get("category", "")
    help_mode = request.GET.get("participation", "")
    upcoming = {}
    for key, number in child.assignment_set.order_by("pk").values_list("lesson", "variation"):
        upcoming[key] = (number+1) % round_count(key)
    groups = {}
    for key, lesson in LESSONS.items():
        if category and lesson["category"] != category:
            continue
        if help_mode and lesson["participation"] != help_mode:
            continue
        groups.setdefault(lesson["category"], []).append((key, lesson, upcoming.get(key, 0)))
    return render(request, "library.html", {
        "child": child, "groups": groups, "category": category, "help_mode": help_mode,
        "categories": sorted({lesson["category"] for lesson in LESSONS.values()}),
        "modes": ["Independent", "Parent required"],
    })


@login_required
@require_http_methods(["GET", "POST"])
def preview(request, pk, key, step):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    lesson = LESSONS.get(key)
    if not lesson or step > len(lesson["items"]):
        raise Http404
    number = requested_round(key, request.GET.get("v", 0))
    lesson = build_round(key, number)
    def preview_url(target):
        url = reverse("preview", args=[pk, key, target])
        return f"{url}?v={number}" if number else url

    finished = step == len(lesson["items"])
    context = {
        "preview": True, "child": child, "key": key, "step": step, "lesson": lesson,
        "feedback_kinds": LessonFeedback.Kind.choices, "finished": finished, "variation": number,
        "next_variant": (number+1) % round_count(key),
    }
    if request.method == "POST" and request.POST.get("action") == "feedback":
        kind = request.POST.get("kind")
        note = request.POST.get("note", "").strip()
        if kind not in LessonFeedback.Kind.values or len(note) > 1500:
            return HttpResponseBadRequest("Choose a feedback type and use at most 1500 characters.")
        LessonFeedback.objects.create(parent=request.user, lesson=key, step=None if finished else step,
                                      kind=kind, note=note, variation=number)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"saved": True})
        messages.success(request, "Feedback saved. Thank you for helping shape this lesson.")
        return redirect(preview_url(step))
    if finished:
        return render(request, "preview_done.html", context)
    item = lesson["items"][step]
    if "shape" in item:
        item = art_item(item)
    context["item"] = item
    if request.method == "POST":
        accepted, artwork = lesson_response(request, lesson, item)
        if accepted:
            if artwork:
                messages.success(request, artwork["feedback"])
            return redirect(preview_url(step+1))
        context["error"] = "Take another look. You can try again."
    return render(request, "play.html", context)


@login_required
def feedback_history(request):
    rows = LessonFeedback.objects.prefetch_related("replies")
    if not request.user.is_staff:
        rows = rows.filter(parent=request.user)
    enabled = FeedbackEmailPreference.objects.filter(parent=request.user, enabled=True).exists()
    return render(request, "feedback_history.html", {"rows": decorate(rows), "notify": enabled})


@login_required
@require_POST
def feedback_preferences(request):
    enabled = request.POST.get("notify") == "on"
    if enabled and not request.user.email:
        messages.error(request, "Add an email address to your account before enabling notifications.")
    else:
        FeedbackEmailPreference.objects.update_or_create(parent=request.user, defaults={"enabled": enabled})
        messages.success(request, "Email preference saved.")
    return redirect("feedback_history")


@login_required
@require_POST
def manage(request, pk):
    child = get_object_or_404(Learner, pk=pk, parent=request.user)
    action = request.POST.get("action")
    if action == "play":
        request.session.flush()
        request.session["child"] = child.pk
    elif action == "assign" and request.POST.get("lesson") in LESSONS:
        assign_lesson(child, request.POST["lesson"])
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
    lesson = row.round_snapshot or LESSONS[row.lesson]
    item = lesson["items"][row.step]
    if "shape" in item:
        item = art_item(item)
    error = ""
    if request.method == "POST":
        current = Assignment.objects.filter(pk=pk, step=row.step, completed=None)
        if request.POST.get("step") != str(row.step):
            return redirect("play", pk)
        accepted, artwork = lesson_response(request, lesson, item)
        if accepted:
            done = row.step+1 == len(lesson["items"])
            updated = current.update(step=F("step")+1, completed=timezone.now() if done else None, artwork=artwork)
            if done and updated:
                messages.success(request, artwork["feedback"] if artwork else f"Finished {lesson['title']}! Well done.")
            return redirect("home") if done else redirect("play", pk)
        current.update(retries=F("retries")+1)
        error = "Take another look. You can try again."
    return render(request, "play.html", {"step": row.step,"lesson": lesson,"item": item,"error": error})
