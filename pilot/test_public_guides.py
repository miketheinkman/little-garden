from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from .models import InviteRequest, ParentInvitation
from .practice import CURRENT_LESSONS
from .public_guides import GALLERY


@override_settings(INVITE_REQUEST_RECIPIENTS=["first@example.org", "second@example.org"],
                   PUBLIC_HOST="testserver", INVITE_ONLY_SIGNUP=True)
class PublicGuideTests(TestCase):
    def test_public_navigation_and_catalog_match(self):
        for page in ("home", "welcome", "curriculum", "how_it_works", "request_invite"):
            response = self.client.get(reverse(page))
            for route in ("curriculum", "how_it_works", "request_invite"):
                self.assertContains(response, reverse(route))
        page = self.client.get(reverse("curriculum"))
        for lesson in CURRENT_LESSONS.values():
            self.assertContains(page, escape(lesson["title"]))
        for key, slug, _ in GALLERY:
            self.assertIn(key, CURRENT_LESSONS)
            self.assertTrue(finders.find(f"guides/{slug}.png"))

    def test_repeated_requests_notify_both_reviewers_once_and_leave_signup_closed(self):
        for email in ("Parent@example.org", "parent@example.org"):
            self.assertRedirects(self.client.post(reverse("request_invite"), {"email": email}),
                                 reverse("invite_received"))
        self.assertEqual(InviteRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["first@example.org", "second@example.org"])
        self.assertIn("parent@example.org", mail.outbox[0].body)
        self.assertFalse(ParentInvitation.objects.exists())
        self.assertContains(self.client.get(reverse("signup")), "Invitation code")

    def test_validation_privacy_and_staff_invitation(self):
        url = reverse("request_invite")
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, {"email": "parent@example.org"}).status_code, 403)
        self.assertContains(self.client.post(url, {"email": "no-at-sign"}), "Enter a valid email")
        self.assertFalse(InviteRequest.objects.exists())
        person = get_user_model().objects.create_user("qa-parent")
        entry = InviteRequest.objects.create(email="parent@example.org")
        queue = reverse("invite_requests")
        self.assertEqual(self.client.get(queue).status_code, 302)
        self.client.force_login(person)
        self.assertEqual(self.client.post(queue, {"entry": entry.pk, "action": "invite"}).status_code, 403)
        person.is_staff = True
        person.save()
        self.assertContains(self.client.get(queue), entry.email)
        for _ in range(2):
            self.client.post(queue, {"entry": entry.pk, "action": "invite"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [entry.email])
        entry.refresh_from_db()
        self.assertIsNotNone(entry.invited_at)

    def test_notification_failure_keeps_request_for_staff_retry(self):
        with patch("pilot.public_guides.send_mail", side_effect=SMTPException):
            self.assertRedirects(self.client.post(reverse("request_invite"), {"email": "parent@example.org"}),
                                 reverse("invite_received"))
        entry = InviteRequest.objects.get()
        self.assertIsNone(entry.notified_at)
        self.client.force_login(get_user_model().objects.create_user("staff", is_staff=True))
        self.client.post(reverse("invite_requests"), {"entry": entry.pk, "action": "notify"})
        entry.refresh_from_db()
        self.assertIsNotNone(entry.notified_at)
        self.assertFalse(ParentInvitation.objects.exists())

    def test_social_icons_and_public_destinations(self):
        from urllib.parse import parse_qs, urlsplit
        from xml.etree import ElementTree

        from .templatetags.social import DESTINATIONS, MANUAL, WELCOME

        sprite = ElementTree.parse(finders.find("brand/share-icons.svg"))
        ids = {symbol.get("id") for symbol in sprite.getroot()}
        manual = {slug for _, slug, _, _ in MANUAL}
        page = self.client.get(reverse("mission") + "?private=family")
        for name, icon, url in DESTINATIONS:
            self.assertIn(icon, ids)
            self.assertContains(page, f'aria-label="Share on {name}"')
            self.assertContains(page, f'href="{escape(url)}"')
            if icon in manual:
                self.assertContains(page, f'id="share-{icon}"')
            else:
                fields = parse_qs(urlsplit(url).query)
                self.assertTrue(any(WELCOME in value for values in fields.values() for value in values))
                self.assertNotIn("private", url)
        session = self.client.session
        session["child"] = 12
        session.save()
        self.assertNotContains(self.client.get(reverse("mission")), 'aria-label="Share Little Garden"')
