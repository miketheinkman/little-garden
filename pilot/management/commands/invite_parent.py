from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from pilot.invitations import code_digest
from pilot.models import InviteRequest, ParentInvitation


class Command(BaseCommand):
    help = "Email a single-use alpha invitation, or revoke an outstanding invitation."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--revoke", action="store_true")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("Enter a valid parent email address.") from exc
        if options["revoke"]:
            count, _ = ParentInvitation.objects.filter(email=email, used_at__isnull=True).delete()
            self.stdout.write("Invitation revoked." if count else "No outstanding invitation.")
            return
        if not settings.INVITE_ONLY_SIGNUP:
            raise CommandError("Use the hosted alpha deployment to send invitations.")
        code = secrets.token_urlsafe(24)
        with transaction.atomic():
            ParentInvitation.objects.update_or_create(email=email, defaults={
                "code_digest": code_digest(code), "used_at": None,
                "expires_at": timezone.now() + timedelta(days=7),
            })
            if get_user_model().objects.filter(email__iexact=email).exists():
                raise CommandError("A parent account already uses that email address.")
            url = f"https://{settings.PUBLIC_HOST}{reverse('signup')}"
            sent = send_mail("Your Little Garden alpha invitation",
                             f"You're invited to try Little Garden with your family.\n\n"
                             f"Open {url} and paste this invitation code:\n\n{code}\n\n"
                             "This code is for your parent account and expires in seven days.",
                             settings.DEFAULT_FROM_EMAIL, [email])
            if sent != 1:
                raise CommandError("The mail service did not accept the invitation.")
            InviteRequest.objects.filter(email=email).update(invited_at=timezone.now())
        self.stdout.write("Invitation submitted to the mail service.")
