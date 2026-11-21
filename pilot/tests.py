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
