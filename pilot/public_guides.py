from datetime import timedelta
from smtplib import SMTPException

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.management import call_command, CommandError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import InviteRequest
from .practice import CURRENT_LESSONS

# The curriculum gallery is captured from these actual lessons by qa.visual.
GALLERY = (
    ("ten-v1", "ten", "How many more counters will fill the ten-frame?"),
    ("lowercase-v1", "trace", "Follow the starting dot to form a lowercase letter."),
    ("water-works-v1", "water", "Tap the valve and press Go to see whether water reaches the garden."),
)


def curriculum(request):
    subjects = {}
    for lesson in CURRENT_LESSONS.values():
        subjects.setdefault(lesson["category"], []).append(lesson)
    gallery = [(CURRENT_LESSONS[key]["title"], f"guides/{slug}.png", caption)
               for key, slug, caption in GALLERY]
    return render(request, "curriculum.html", {"subjects": subjects, "gallery": gallery,
                                               "lesson_count": len(CURRENT_LESSONS)})


class RequestForm(forms.Form):
    email = forms.EmailField(label="Parent or caregiver email", max_length=254,
                            widget=forms.EmailInput(attrs={"autocomplete": "email"}))


def notify_reviewers(entry):
    if not settings.INVITE_REQUEST_RECIPIENTS:
        return False
    origin = getattr(settings, "PUBLIC_HOST", "")
    queue_url = f"https://{origin}{reverse('invite_requests')}" if origin else reverse("invite_requests")
    try:
        accepted = send_mail("Little Garden · New alpha invite request",
                             f"A parent requested an invitation for {entry.email}.\n\n"
                             f"Review requests in the staff dashboard: {queue_url}",
                             settings.DEFAULT_FROM_EMAIL, settings.INVITE_REQUEST_RECIPIENTS)
    except (OSError, SMTPException):
        return False
    if accepted:
        entry.notified_at = timezone.now()
        entry.save(update_fields=["notified_at"])
    return bool(accepted)


@never_cache
@require_http_methods(["GET", "POST"])
def request_invite(request):
    form = RequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        entry, created = InviteRequest.objects.get_or_create(email=form.cleaned_data["email"].lower())
        # Keep every request available to staff even during a burst of submissions.
        if created:
            recent = InviteRequest.objects.filter(notified_at__gte=timezone.now() - timedelta(minutes=10))
            if recent.count() < 20:
                notify_reviewers(entry)
        return redirect("invite_received")
    return render(request, "request_invite.html", {"form": form})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def invite_requests(request):
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == "POST":
        with transaction.atomic():
            pk = forms.IntegerField(min_value=1)
            try:
                entry_id = pk.clean(request.POST.get("entry"))
            except forms.ValidationError:
                return redirect("invite_requests")
            entry = get_object_or_404(InviteRequest.objects.select_for_update(), pk=entry_id)
            if request.POST.get("action") == "notify" and not entry.notified_at:
                ok = notify_reviewers(entry)
                messages.info(request, "Notification submitted." if ok else
                              "Notification could not be sent. Check the reviewer inbox settings and retry.")
            elif request.POST.get("action") == "invite" and not entry.invited_at and settings.INVITE_ONLY_SIGNUP:
                try:
                    call_command("invite_parent", entry.email)
                except (CommandError, SMTPException, OSError):
                    messages.error(request, "Invitation could not be issued. Check the account and mail settings.")
                else:
                    messages.success(request, "Invitation submitted.")
        return redirect("invite_requests")
    page = Paginator(InviteRequest.objects.order_by("-requested_at", "-pk"), 40).get_page(request.GET.get("page"))
    return render(request, "invite_requests.html", {"page": page, "invite_only": settings.INVITE_ONLY_SIGNUP})
