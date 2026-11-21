from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Assignment, Learner
from .views import LESSONS


class FamilyPilotTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("parent")
        self.client.force_login(self.parent)
        self.child = Learner.objects.create(parent=self.parent, nickname="Sprout")
        self.sibling = Learner.objects.create(parent=self.parent, nickname="Clover")
        self.manage = f"/children/{self.child.pk}/"

    def test_assign_resume_complete_and_report(self):
        self.client.post(self.manage, {"action": "assign", "lesson": "keys-v1"})
        row = Assignment.objects.get()
        url = f"/play/{row.pk}/"
        self.client.post(self.manage, {"action": "play"})
        self.assertContains(self.client.get("/"), "Sprout")
        self.assertContains(self.client.post(url, {"step": 0, "answer": "Z"}), "try again")
        for i, letter in enumerate("sat"):
            self.client.post(url, {"step": i, "answer": letter})
            self.client.post(url, {"step": i, "answer": letter})
        row.refresh_from_db()
        self.assertEqual((row.step, row.retries), (3, 1))
        self.assertIsNotNone(row.completed)
        self.assertContains(self.client.get("/"), "queue is clear")
        self.client.force_login(self.parent)
        self.assertContains(self.client.get("/"), "3 steps completed")

    def test_child_scope_and_parent_gate(self):
        other = self.sibling.assignment_set.create(lesson="keys-v1")
        self.client.post(self.manage, {"action": "play"})
        self.assertEqual(self.client.get(f"/play/{other.pk}/").status_code, 404)
        self.assertEqual(self.client.post(self.manage, {"action": "assign"}).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_household_boundary(self):
        outsider = get_user_model().objects.create_user("another-parent")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(self.manage, {"action": "play"}).status_code, 404)

    def test_library_and_reordering(self):
        for key in LESSONS:
            self.client.post(self.manage, {"action": "assign", "lesson": key})
        last = self.child.assignment_set.last()
        self.client.post(self.manage, {"action": "first", "row": last.pk})
        self.assertEqual(self.child.assignment_set.first(), last)
        self.client.post(self.manage, {"action": "play"})
        for row in self.child.assignment_set.all():
            response = self.client.get(f"/play/{row.pk}/")
            self.assertContains(response, LESSONS[row.lesson]["items"][0]["prompt"], html=True)


class RecoveryTests(TestCase):
    def test_reset_and_single_use(self):
        from django.core import mail
        import re
        parent = get_user_model().objects.create_user("fern", email="fern@example.org", password="before-342!")
        self.assertContains(self.client.get("/login/"), "Forgot password?")
        response = self.client.post("/password/reset/", {"email": parent.email})
        self.assertRedirects(response, "/password/requested/")
        path = re.search(r"http://testserver(/\S+)", mail.outbox[0].body)[1]
        form = self.client.get(path, follow=True)
        self.assertContains(form, "Save password")
        response = self.client.post(form.request["PATH_INFO"], {
            "new_password1": "after-recovery-549!", "new_password2": "after-recovery-549!",
        })
        self.assertRedirects(response, "/password/updated/")
        self.assertTrue(self.client.login(username="fern", password="after-recovery-549!"))
        self.assertContains(self.client.get(path, follow=True), "invalid or expired")
        self.assertRedirects(self.client.post("/password/reset/", {"email": "unknown@example.org"}), "/password/requested/")
        self.assertEqual(len(mail.outbox), 1)

    def test_signup_stores_email_and_change_requires_password(self):
        self.client.post("/signup/", {"username": "spruce", "email": "spruce@example.org",
                                     "password1": "Green-tree-435!", "password2": "Green-tree-435!"})
        parent = get_user_model().objects.get(username="spruce")
        self.assertEqual(parent.email, "spruce@example.org")
        fields = {"email": "updated@example.org", "password": "wrong"}
        self.assertContains(self.client.post("/account/email/", fields), "Check your current password")
        fields["password"] = "Green-tree-435!"
        self.assertRedirects(self.client.post("/account/email/", fields), "/")
        parent.refresh_from_db()
        self.assertEqual(parent.email, fields["email"])
