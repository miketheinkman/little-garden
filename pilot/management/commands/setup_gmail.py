import json
import os
from email.utils import formataddr
from getpass import getpass
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from smtplib import SMTPException

from pilot.mail import gmail_connection


class Command(BaseCommand):
    help = "Test Gmail SMTP and save the credential privately for local password resets."

    def add_arguments(self, parser):
        parser.add_argument("sender")
        parser.add_argument("recipient")

    def handle(self, sender, recipient, **options):
        if settings.EMAIL_HOST:
            raise CommandError("An SMTP host is already configured in the environment.")
        try:
            for address in (sender, recipient):
                validate_email(address)
        except ValidationError as error:
            raise CommandError("Enter a valid sender and recipient.") from error

        password = "".join(getpass("Google app password (hidden): ").split())
        if len(password) != 16:
            raise CommandError("Enter the 16-character Google app password.")
        try:
            with gmail_connection(sender, password) as connection:
                message = EmailMessage(
                    "Little Garden email delivery test",
                    "Little Garden can now send password reset emails from this account.",
                    formataddr(("Little Garden", sender)), [recipient], connection=connection,
                )
                message.send()
        except (OSError, SMTPException) as error:
            raise CommandError(f"Gmail delivery failed ({type(error).__name__}). Check the app password and network.") from None

        path = settings.GARDEN_GMAIL_FILE
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as private:
            json.dump({"sender": sender, "password": password}, private)
        os.replace(private.name, path)
        self.stdout.write(self.style.SUCCESS("Gmail accepted the test message. Little Garden will now use Gmail for password resets."))
