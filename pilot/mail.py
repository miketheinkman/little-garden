import json
from email.utils import formataddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.filebased import EmailBackend as FileBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


def gmail_connection(sender, password):
    return SMTPBackend(host="smtp.gmail.com", port=587, use_tls=True,
                       username=sender, password=password, timeout=15)


class LocalMailBackend(BaseEmailBackend):
    """Use the locally configured Gmail sender, or the pilot's private outbox."""

    def send_messages(self, messages):
        try:
            config = json.loads(settings.GARDEN_GMAIL_FILE.read_text())
        except FileNotFoundError:
            return FileBackend(fail_silently=self.fail_silently).send_messages(messages)

        sender = config["sender"]
        for message in messages:
            message.from_email = formataddr(("Little Garden", sender))
        with gmail_connection(sender, config["password"]) as connection:
            return connection.send_messages(messages)
