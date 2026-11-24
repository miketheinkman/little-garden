import re
import random
from collections import defaultdict
from datetime import timedelta

from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import ParentSignupForm, RecoveryEmailForm
from django.db import connection, transaction
from django.core.paginator import Paginator
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from .models import Assignment, Learner, LessonFeedback, FeedbackEmailPreference

from .themes import THEMES, THEME_CHOICES, assignment_lesson, summary, themed_round
from .puzzles import parse_moves, simulate, hint
from .discovery import PATCH, discovery_round, letter_selection
from .assignments import assign_lesson, suggested_round, question_set
from .scheduling import release_due
from .paint import mixture_matches
from .table_games import table_answer
from .audio import lesson_clips
from .art import art_item, evaluate
from .coview import recent_response
from .models import FONT_CHOICES, SkillSample
from .progression import FIT_LABELS, Progress, item_score, record_tier
from .practice import CURRENT_LESSONS, CURRENT_VERSION, LESSONS, build_round, round_count


def puzzle_action(request, item, row=None):
    board = item["board"]
    moves = parse_moves(board, request.POST.get("moves", ""))
    if moves is None:
        return HttpResponseBadRequest("Reopen this puzzle to load its pieces.")
    action = request.POST["action"]
    if action == "run":
        return JsonResponse(simulate(board, moves))
    if row:
        flag = 1 if action == "hint" else 2
        Assignment.objects.filter(pk=row.pk, step=row.step, completed=None, removed_at=None).update(
            puzzle_help=F("puzzle_help").bitor(flag))
    return JsonResponse({"spot": hint(board, moves) if action == "hint" else None})


def lesson_response(request, lesson, item):
    if lesson.get("tool") == "dots":
        return request.POST.get("tool_state") == item["answer"], None
    if lesson.get("tool") == "sort":
        return request.POST.get("tool_state") == ",".join(str(p["bin"]) for p in item["pieces"]), None
    if lesson.get("tool") == "paint-mix":
        return mixture_matches(item, request.POST.get("tool_state", "")), None
    if lesson["kind"] in {"balance", "memory"}:
        return table_answer(item, request.POST.get("tool_state", "")), None
    if "board" in item:
        moves = parse_moves(item["board"], request.POST.get("moves", ""))
        return moves is not None and simulate(item["board"], moves)["success"], None
    if "shape" in item:
        pixels = request.POST.get("pixels", "")
        feedback = evaluate(lesson["kind"], item["mask"], pixels)
        if feedback is None:
            return False, None
        return True, {"pixels": pixels, "feedback": feedback, "mask": item["mask"], "kind": lesson["kind"]}
    submitted = request.POST.get("answer", "")
    if "carrots" in item and request.POST.get("shares"):
        shares = request.POST["shares"].split(",")
        allowed = [str(item["carrots"] // item["rabbits"])] * item["rabbits"]
        if shares not in (["0"] * item["rabbits"], allowed):
            return False, None
    if lesson.get("tool") == "shift":
        return submitted == item["answer"], None
    return submitted.casefold() in {answer.casefold() for answer in [item["answer"], *item.get("also_accept", [])]}, None


def success_result(lesson):
    return "finished" if lesson["kind"] in {"draw", "color", "mirror", "adult"} else "correct"


def answer_transition(request, destination, lesson, accepted=False, tier_gain=None):
    if request.headers.get("Accept") != "application/json":
        return redirect(destination)
    result = success_result(lesson) if accepted else "advance"
    return JsonResponse({"result": result, "next": destination, **({"tier_gain": tier_gain} if tier_gain else {})})


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
            release_due(child)
            child.queue = decorate(child.assignment_set.filter(completed=None, removed_at=None), child)
            progress = Progress(child)
            for row in child.queue:
                row.fit_label = progress.label(LESSONS[row.lesson])
                row.level = LESSONS[row.lesson]["level"]
            child.suggestions = [] if child.queue else progress.recommendations()
            active = {CURRENT_VERSION.get(row.lesson, row.lesson) for row in child.queue}
            child.checkins = [check for check in progress.checkins() if check["key"] not in active]
            child.charts = progress.charts()
            child.round_count = len(progress.recent)
            child.timeline = progress.timeline()
            child.record = decorate(child.assignment_set.filter(
                completed__gte=timezone.now()-timedelta(days=7)).order_by("-completed"))
        return render(request, "parent.html", {"learners": learners, "lessons": LESSONS, "theme_choices": THEME_CHOICES, "fonts": FONT_CHOICES})
    child = Learner.objects.filter(pk=request.session.get("child")).first()
    if child:
        release_due(child)
        queue = decorate(child.assignment_set.filter(completed=None, removed_at=None), child)
        progress = Progress(child)
        child.charts = progress.charts()
        child.round_count = len(progress.recent)
        return render(request, "child.html", {"child": child, "appearance": child.appearance, "world": THEMES[child.lesson_theme], "queue": queue,
                      "suggestions": [] if queue else progress.recommendations()})
    return render(request, "welcome.html")


def decorate(rows, child=None):
    rows = list(rows)
    for row in rows:
        row.info = assignment_lesson(row, child.lesson_theme if child else None) if isinstance(row, Assignment) else LESSONS[row.lesson]
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


def active_lesson_keys(child):
    keys = child.assignment_set.filter(completed=None, removed_at=None).values_list("lesson", flat=True)
    return {CURRENT_VERSION.get(key, key) for key in keys}


@transaction.atomic
def queue_available(child, keys, variation=None, letters=None):
    # Serialize single and bulk adds before reading the queue, including on SQLite.
    Learner.objects.filter(pk=child.pk).update(nickname=F("nickname"))
    active = active_lesson_keys(child)
    added = []
    for key in keys:
        current = CURRENT_VERSION.get(key, key)
        if current not in active:
            assign_lesson(child, key, variation, letters)
            active.add(current)
            added.append(key)
    return added, active


@login_required
@require_http_methods(["GET", "POST"])
def library(request, pk):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    release_due(child)
    category = request.GET.get("category", "")
    help_mode = request.GET.get("participation", "")
    tier = request.GET.get("tier", "")
    fit_label = request.GET.get("fit", "")
    progress = Progress(child)
    matching = {key: lesson for key, lesson in CURRENT_LESSONS.items()
                if (not category or lesson["category"] == category)
                and (not help_mode or lesson["participation"] == help_mode)
                and (not tier or tier == ("checkin" if lesson.get("checkin") else str(lesson["level"])))
                and (not fit_label or progress.label(lesson) == fit_label)}
    if request.method == "POST":
        if request.POST.get("action") == "all":
            added, active = queue_available(child, matching)
            note = f"Added {len(added)} lesson{'s' if len(added) != 1 else ''} to {child.nickname}’s queue."
        else:
            key = request.POST.get("lesson")
            if key not in LESSONS:
                return HttpResponseBadRequest("Choose a lesson from the library.")
            variation = requested_round(key, request.POST["variation"]) if "variation" in request.POST else None
            try:
                letters = letter_selection(request.POST["letters"]) if key == PATCH and "letters" in request.POST else None
            except ValueError as error:
                return HttpResponseBadRequest(str(error))
            added, active = queue_available(child, [key], variation, letters)
            title = summary(key, LESSONS[key], child.lesson_theme)["title"]
            note = (f"{title} added to {child.nickname}’s queue." if added else
                    f"{title} is already in {child.nickname}’s queue.")
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"active": sorted(active), "message": note})
        messages.success(request, note)
        return redirect(request.get_full_path())

    active = active_lesson_keys(child)
    histories = defaultdict(list)
    for key, number in child.assignment_set.order_by("pk").values_list("lesson", "variation"):
        key = CURRENT_VERSION.get(key, key)
        histories[key].append(number)
    today = timezone.localdate()
    groups = {}
    for key, lesson in matching.items():
        if key not in active:
            info = dict(summary(key, lesson, child.lesson_theme))
            completions = progress.attempted.get(key)
            if completions:
                info["last_completed"] = completions[0]
                days = (today - timezone.localdate(completions[0])).days
                info["last_completed_label"] = {0: "today", 1: "yesterday"}.get(days, f"{days} days ago")
            groups.setdefault(lesson["category"], []).append((key, info, suggested_round(child, key, histories[key]), progress.label(lesson)))
    return render(request, "library.html", {
        "tier": tier, "tiers": ["1", "2", "3", "4", "5"], "fit_label": fit_label, "fits": FIT_LABELS,
        "child": child, "groups": groups, "category": category, "help_mode": help_mode,
        "world": THEMES[child.lesson_theme], "available": len(matching.keys() - active), "matches": bool(matching),
        "categories": sorted({lesson["category"] for lesson in CURRENT_LESSONS.values()}),
        "modes": ["Independent", "Parent required"],
    })


@login_required
def assignment_history(request, pk):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    rows = child.assignment_set.annotate(
        history_date=Coalesce("removed_at", "completed", "assigned_at"),
        status=Case(
            When(removed_at__isnull=False, then=Value("Removed")),
            When(completed__isnull=False, skipped__gt=0, then=Value("Finished with skips")),
            When(completed__isnull=False, then=Value("Completed")),
            When(Q(step__gt=0) | Q(retries__gt=0) | Q(round_snapshot__has_key="_opened_theme"),
                 then=Value("In progress")),
            default=Value("Queued"),
        ),
    )
    versions = {}
    for key in rows.order_by().values_list("lesson", flat=True).distinct():
        versions.setdefault(CURRENT_VERSION.get(key, key), []).append(key)
    lesson_options = sorted(((key, summary(key, LESSONS[key], child.lesson_theme)["title"]) for key in versions),
                            key=lambda option: option[1])
    months = rows.datetimes("history_date", "month", order="DESC")
    month_options = {date.strftime("%Y-%m"): date for date in months}
    month = request.GET.get("month", "")
    lesson = request.GET.get("lesson", "")
    status = request.GET.get("status", "")
    if month:
        date = month_options.get(month)
        rows = rows.filter(history_date__year=date.year, history_date__month=date.month) if date else rows.none()
    if lesson:
        rows = rows.filter(lesson__in=versions.get(lesson, []))
    if status:
        rows = rows.filter(status=status)
    page = Paginator(rows.order_by(F("history_date").desc(nulls_last=True), "-pk"), 20).get_page(request.GET.get("page"))
    page.object_list = decorate(page.object_list, child)
    return render(request, "assignment_history.html", {
        "child": child, "page": page, "lesson_options": lesson_options, "month_options": month_options,
        "statuses": ("Completed", "Finished with skips", "In progress", "Queued", "Removed"),
        "month": month, "lesson": lesson, "status": status,
    })


@login_required
@require_http_methods(["GET", "POST"])
def preview(request, pk, key, step):
    child = get_object_or_404(Learner, parent=request.user, pk=pk)
    lesson = LESSONS.get(key)
    if not lesson:
        raise Http404
    number = requested_round(key, request.GET.get("v", 0))
    if request.GET.get("shuffle") == "1":
        selected = random.SystemRandom().randrange(round_count(key)-1)
        query = request.GET.copy()
        query.pop("shuffle")
        query["v"] = str(selected + (selected >= number))
        return redirect(reverse("preview", args=[pk, key, 0]) + "?" + query.urlencode())
    try:
        letters = letter_selection(request.GET["letters"]) if key == PATCH and "letters" in request.GET else None
    except ValueError as error:
        return HttpResponseBadRequest(str(error))
    raw = discovery_round(key, number, letters) if letters else build_round(key, number)
    if step > len(raw["items"]):
        raise Http404
    lesson = themed_round(key, raw, child.lesson_theme, number)
    letter_query = f"&letters={letters}" if letters else ""
    def preview_url(target):
        url = reverse("preview", args=[pk, key, target])
        return f"{url}?v={number}{letter_query}" if number or letters else url

    finished = step == len(lesson["items"])
    context = {
        "preview": True, "appearance": child.appearance, "child": child, "key": key, "step": step, "lesson": lesson,
        "letter_query": letter_query, "feedback_kinds": LessonFeedback.Kind.choices, "finished": finished, "variation": number,
        "next_variant": (number+1) % round_count(key),
        "already_queued": CURRENT_VERSION.get(key, key) in active_lesson_keys(child),
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
    context.update(lesson_clips(item, key))
    if request.method == "POST":
        if "board" in item and request.POST.get("action") in {"run", "hint", "parent"}:
            return puzzle_action(request, item)
        if request.POST.get("action") == "skip":
            return redirect(preview_url(step+1))
        accepted, artwork = lesson_response(request, lesson, item)
        if accepted or lesson.get("checkin") and request.POST.get("answer", "").strip():
            if artwork:
                messages.success(request, artwork["feedback"])
            return answer_transition(request, preview_url(step+1), lesson, accepted)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"result": "retry"})
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
    release_due(child)
    action = request.POST.get("action")
    if action == "play":
        request.session.flush()
        request.session["child"] = child.pk
    elif action in {"appearance", "reset-appearance"}:
        accent, font = "", "default"
        if action == "appearance":
            accent = request.POST.get("accent", "") if request.POST.get("use_accent") else ""
            font = request.POST.get("font", "default")
            if (accent and not re.fullmatch(r"#[0-9a-fA-F]{6}", accent)) or font not in dict(FONT_CHOICES):
                return HttpResponseBadRequest("Choose a valid color and font.")
        child.accent, child.font = accent.lower(), font
        child.save(update_fields=["accent", "font"])
        messages.success(request, f"Saved {child.nickname}’s lesson appearance.")
    elif action == "lesson-audio":
        child.autoplay_directions = request.POST.get("autoplay_directions") == "on"
        child.save(update_fields=["autoplay_directions"])
        messages.success(request, f"Saved {child.nickname}’s lesson audio setting.")
    elif action == "theme":
        theme = request.POST.get("theme")
        if theme not in THEMES:
            return HttpResponseBadRequest("Choose a lesson theme.")
        child.lesson_theme = theme
        child.save(update_fields=["lesson_theme"])
        messages.success(request, f"{child.nickname}’s lesson theme is {THEMES[theme]['label']}.")
    elif action == "assign" and request.POST.get("lesson") in LESSONS:
        queue_available(child, [request.POST["lesson"]])
    elif action == "remove":
        try:
            row_id = int(request.POST.get("row", ""))
        except ValueError:
            return HttpResponseBadRequest("Choose an assignment from the queue.")
        child.assignment_set.filter(pk=row_id, completed=None, removed_at=None).update(removed_at=timezone.now())
    elif action == "first":
        row = get_object_or_404(child.assignment_set, pk=request.POST["row"], completed=None, removed_at=None)
        first = child.assignment_set.filter(completed=None, removed_at=None).first()
        row.position = first.position-1
        row.save(update_fields=["position"])
    else:
        return HttpResponseBadRequest("Unknown action.")
    return redirect("home")


@require_POST
@transaction.atomic
def start_suggestion(request):
    if request.user.is_authenticated:
        raise Http404
    pk = request.session.get("child")
    # Acquire the shared learner write lock before checking the empty queue (also on SQLite).
    if not Learner.objects.filter(pk=pk).update(nickname=F("nickname")):
        raise Http404
    child = Learner.objects.get(pk=pk)
    release_due(child)
    if child.assignment_set.filter(completed=None, removed_at=None).exists():
        return redirect("home")
    key = request.POST.get("lesson")
    if key not in {entry["key"] for entry in Progress(child).recommendations()}:
        return redirect("home")
    return redirect("play", assign_lesson(child, key).pk)


def key_pace(request, catalog, item):
    if catalog["strand"] != "Keyboard use" or catalog["kind"] not in {"key", "type"}:
        return None
    try:
        elapsed = int(request.POST.get("active_ms", ""))
    except ValueError:
        return None
    if not 1 <= elapsed <= 3_600_000:
        return None
    return max(1, round(elapsed / len(item["answer"])))


def play(request, pk):
    if request.user.is_authenticated:
        return redirect("home")
    row = get_object_or_404(Assignment.objects.select_related("learner"), pk=pk, learner_id=request.session.get("child"))
    if row.completed or row.removed_at:
        return redirect("home")
    raw = row.round_snapshot or LESSONS[row.lesson]
    if "_opened_theme" not in raw:
        # Pin the first rendered theme so a parent changing it cannot change an answer mid-round.
        theme = "garden" if row.step or row.retries or request.method == "POST" else row.learner.lesson_theme
        snapshot = dict(raw, _opened_theme=theme)
        if Assignment.objects.filter(pk=row.pk, round_snapshot=row.round_snapshot).update(round_snapshot=snapshot):
            row.round_snapshot = snapshot
        else:
            row.refresh_from_db()
            if row.completed or row.removed_at:
                return redirect("home")
    lesson = assignment_lesson(row)
    item = lesson["items"][row.step]
    if "shape" in item:
        item = art_item(item)
    error = ""
    if request.method == "POST":
        current = Assignment.objects.filter(pk=pk, step=row.step, completed=None, removed_at=None)
        if request.POST.get("step") != str(row.step):
            return redirect("play", pk)
        if "board" in item and request.POST.get("action") in {"run", "hint", "parent"}:
            return puzzle_action(request, item, row)
        skip = request.POST.get("action") == "skip"
        accepted, artwork = (False, None) if skip else lesson_response(request, lesson, item)
        catalog = LESSONS[row.lesson]
        checkin = catalog.get("checkin", False)
        if checkin and not skip and not request.POST.get("answer", "").strip():
            return redirect("play", pk)
        advance = skip or accepted or checkin
        done = advance and row.step+1 == len(lesson["items"])
        tier_gain = None
        with transaction.atomic():
            if connection.features.has_select_for_update:
                Learner.objects.select_for_update().get(pk=row.learner_id)
            changes = {"retries": F("retries") + int(not accepted and not skip)}
            if skip:
                changes["skipped"] = F("skipped") + 1
            if advance:
                changes.update(step=F("step")+1, completed=timezone.now() if done else None)
                if artwork:
                    changes["artwork"] = artwork
            updated = current.update(**changes)
            help_used = 0
            if updated and advance and "board" in item:
                # The guarded update holds the row through reading and clearing this step's help.
                saved = Assignment.objects.filter(pk=pk)
                help_used = saved.values_list("puzzle_help", flat=True).get()
                if help_used:
                    saved.update(puzzle_help=0)
            score = item_score(lesson["kind"], artwork)
            if "board" in item:
                score = 100 if accepted else None
            if updated and not skip and score is not None:
                sample, created = SkillSample.objects.get_or_create(
                    assignment=row, step=row.step, defaults={
                        "strand": catalog["strand"], "level": item.get("level",catalog["level"]),
                        "score": score if accepted else 0, "puzzle_help": help_used,
                        "ms_per_key": key_pace(request, catalog, item) if accepted else None,
                    })
                if created and not help_used:
                    milestone = record_tier(sample, row.learner_id)
                    if accepted:
                        tier_gain = milestone
        if updated:
            if skip:
                action = "Skipped"
            elif lesson.get("tool") == "sort":
                action = "Sorted the baskets" if accepted else "Tried sorting the baskets"
            elif lesson["kind"] in {"key", "choice", "type"}:
                action = "Answered " + request.POST.get("answer", "")[:80]
            else:
                action = "Finished" if advance else "Tried again"
            celebration = success_result(lesson) if accepted and request.headers.get("Accept") == "application/json" else None
            transaction.on_commit(lambda: recent_response(row, lesson["title"], action, celebration, request.POST, tier_gain), robust=True)
        if done and updated:
            messages.success(request, artwork["feedback"] if artwork else f"Finished {lesson['title']}! Well done.")
        if advance or not updated:
            destination = reverse("home") if done else reverse("play", args=[pk])
            return answer_transition(request, destination, lesson, bool(updated and accepted), tier_gain)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"result": "retry"})
        error = "Take another look. You can try again."
    return render(request, "play.html", {**lesson_clips(item, row.lesson), "key": row.lesson, "autoplay_directions": row.learner.autoplay_directions and not error, "appearance": row.learner.appearance, "assignment_id": row.pk, "puzzle_help": row.puzzle_help, "time_keys": LESSONS[row.lesson]["strand"] == "Keyboard use", "step": row.step,"lesson": lesson,"item": item,"error": error})
