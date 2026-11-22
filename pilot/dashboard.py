import uuid
from smtplib import SMTPException

from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from .models import Assignment, LessonFeedback, FeedbackEmailPreference, FeedbackReply
from .practice import CURRENT_VERSION, FIVE_PROMPT_ROUNDS, LESSONS


def review_feedback(request):
    try:
        feedback_id = int(request.POST.get("feedback", ""))
    except ValueError:
        return HttpResponseBadRequest("Select a feedback note.")
    feedback = get_object_or_404(LessonFeedback, pk=feedback_id)
    action = request.POST.get("action")
    if action == "reply":
        body = request.POST.get("reply", "").strip()
        if not body or len(body) > 2000:
            return HttpResponseBadRequest("Enter a reply of 1 to 2000 characters.")
        try:
            submission = uuid.UUID(request.POST.get("submission", ""))
        except ValueError:
            return HttpResponseBadRequest("Reload the reply form and try again.")
    elif action != "read":
        return HttpResponseBadRequest("Unknown feedback action.")

    with transaction.atomic():
        changed = LessonFeedback.objects.filter(pk=feedback.pk, read_at=None).update(read_at=timezone.now())
        if action == "reply":
            _, changed = FeedbackReply.objects.get_or_create(
                feedback=feedback, submission=submission,
                defaults={"reviewer": request.user, "text": body},
            )
    if changed and FeedbackEmailPreference.objects.filter(parent_id=feedback.parent_id, enabled=True).exists():
        parent_email = feedback.parent.email
        event = "received a reply" if action == "reply" else "been marked as read"
        url = request.build_absolute_uri(reverse("feedback_history")) + f"#note-{feedback.pk}"
        invitation = "Open Lesson feedback in your Family garden."
        if request.get_host().split(":")[0] not in ("localhost", "127.0.0.1"):
            invitation += f" {url}"
        if parent_email:
            try:
                send_mail("Little Garden feedback update",
                          f"Your lesson feedback has {event}. {invitation}\n\n"
                          "You can change notification preferences on the same page.",
                          None, [parent_email])
            except (SMTPException, OSError):
                messages.warning(request, "The update was saved, but the email could not be sent.")
    messages.success(request, "Reply saved." if action == "reply" else "Marked as read.")
    return redirect(request.get_full_path() + "#family-feedback")


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def dashboard(request):
    if not (request.user.is_staff or request.user.has_perm("pilot.review_lessons")):
        raise PermissionDenied
    if request.method == "POST":
        return review_feedback(request)
    selected = request.GET.get("lesson", "")
    flag = request.GET.get("flag", "")
    catalog = {
        key: dict(lesson, title=f"{lesson['title']} ({len(lesson['items'])} prompts)")
        if key in CURRENT_VERSION or key in FIVE_PROMPT_ROUNDS else lesson
        for key, lesson in LESSONS.items()
    }
    lessons = {key: lesson for key, lesson in catalog.items() if not selected or selected == key}
    assignments = Assignment.objects.filter(lesson__in=lessons, removed_at=None)
    notes = LessonFeedback.objects.filter(lesson__in=lessons)
    metrics = {
        row["lesson"]: row for row in assignments.order_by().values("lesson").annotate(
            assigned=Count("id"),
            started=Count("id", filter=Q(step__gt=0) | Q(retries__gt=0) | Q(completed__isnull=False)),
            finished=Count("id", filter=Q(completed__isnull=False, skipped=0)),
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
    state = request.GET.get("state", "")
    if state in ("read", "unread"):
        notes = notes.filter(read_at__isnull=state == "unread")
    page = Paginator(notes.prefetch_related("replies"), 15).get_page(request.GET.get("page"))
    for note in page:
        note.title = lessons[note.lesson]["title"]
        note.submission = uuid.uuid4()
    return render(request, "dashboard.html", {
        "lessons": catalog, "selected": selected, "flags": LessonFeedback.Kind.choices,
        "flag": flag, "state": state, "rows": rows, "notes": page, "totals": totals,
    })
