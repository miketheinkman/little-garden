from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .invitations import code_digest
from .models import ParentInvitation


@override_settings(INVITE_ONLY_SIGNUP=True, PUBLIC_HOST="alpha.example.org",
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationTests(TestCase):
    email = "invitee@example.org"
    fields = {"username": "sprout", "email": "other@example.org",
              "password1": "Garden-families-45", "password2": "Garden-families-45"}

    def invite(self):
        call_command("invite_parent", self.email, verbosity=0)
        message = mail.outbox[-1]
        self.assertEqual(message.to, [self.email])
        code = message.body.split("\n\n")[2]
        self.assertIn("https://alpha.example.org/signup/", message.body)
        self.assertEqual(ParentInvitation.objects.get(email=self.email).code_digest, code_digest(code))
        return code

    def test_direct_signup_requires_code(self):
        self.assertNotContains(self.client.get("/signup/"), 'name="password1"')
        for data in (self.fields, {**self.fields, "code": "made-up"}):
            response = self.client.post("/signup/", data)
            self.assertContains(response, "Invitation code")
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertFalse(get_user_model().objects.exists())

    def test_single_use_and_email_binding(self):
        code = self.invite()
        other = Client()
        for client in (self.client, other):
            self.assertRedirects(client.post("/signup/", {"code": code}), "/signup/")
        self.client.post("/signup/", {**self.fields, "password2": "wrong"})
        self.assertTrue(ParentInvitation.available().exists())
        self.assertRedirects(self.client.post("/signup/", self.fields), "/")
        user = get_user_model().objects.get()
        self.assertEqual(user.email, self.email)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertNotContains(other.post("/signup/", {**self.fields, "username": "another"}), 'name="password1"')
        self.assertContains(Client().post("/signup/", {"code": code}), "invalid or has expired")
        with self.assertRaises(CommandError):
            self.invite()
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_expiry_replacement_and_revocation(self):
        first = self.invite()
        self.client.post("/signup/", {"code": first})
        second = self.invite()
        self.assertContains(self.client.post("/signup/", self.fields), "no longer available")
        self.assertContains(self.client.post("/signup/", {"code": first}), "invalid or has expired")
        self.client.post("/signup/", {"code": second})
        ParentInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.client.post("/signup/", self.fields), "no longer available")
        third = self.invite()
        self.client.post("/signup/", {"code": third})
        call_command("invite_parent", "--revoke", self.email)
        self.assertContains(self.client.post("/signup/", self.fields), "no longer available")
        self.assertFalse(get_user_model().objects.exists())

    def test_failed_resend_keeps_previous_code(self):
        original = self.invite()
        with patch("pilot.management.commands.invite_parent.send_mail", side_effect=OSError):
            with self.assertRaises(OSError):
                self.invite()
        self.assertTrue(ParentInvitation.available().filter(code_digest=code_digest(original)).exists())
