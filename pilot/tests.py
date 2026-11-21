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


class LibraryTests(TestCase):
    def setUp(self):
        parent = get_user_model().objects.create_user("library-parent")
        self.client.force_login(parent)
        self.child = Learner.objects.create(parent=parent, nickname="Fern")
        self.library = f"/children/{self.child.pk}/library/"

    def test_filter_and_assign(self):
        url = self.library + "?category=Science+%26+discovery&participation=Parent+required"
        response = self.client.get(url)
        self.assertContains(response, "Shadow detectives")
        self.assertNotContains(response, "Cloud-watch log")
        self.assertRedirects(self.client.post(url, {"lesson": "shadow-v1"}), url)
        self.assertEqual(self.child.assignment_set.get().lesson, "shadow-v1")

    def test_previews_can_be_completed_without_learner_records(self):
        for key, lesson in LESSONS.items():
            for step, item in enumerate(lesson["items"]):
                url = f"{self.library}{key}/preview/{step}/"
                self.assertContains(self.client.get(url), item["prompt"], html=True)
                response = self.client.post(url, {"answer": item["answer"]}, follow=True)
            self.assertContains(response, "Preview complete")
        self.assertFalse(Assignment.objects.exists())

    def test_preview_is_household_scoped(self):
        outsider = get_user_model().objects.create_user("outside")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.library+"market-v1/preview/0/").status_code, 404)

    def test_preview_feedback_is_scoped_and_separate_from_progress(self):
        from .models import LessonFeedback
        url = self.library + "keys-v1/preview/1/"
        data = {"action": "feedback", "kind": "confusing", "note": "The prompt needs a picture."}
        self.assertEqual(self.client.post(url, data, HTTP_ACCEPT="application/json").json(), {"saved": True})
        feedback = LessonFeedback.objects.get()
        self.assertEqual((feedback.step, feedback.lesson), (1, "keys-v1"))
        self.assertContains(self.client.get("/feedback/"), data["note"])
        end = self.library + "keys-v1/preview/3/"
        self.assertRedirects(self.client.post(end, {"action": "feedback", "kind": "worked"}), end)
        self.assertTrue(LessonFeedback.objects.filter(step=None, kind="worked").exists())
        self.assertFalse(Assignment.objects.exists())
        outsider = get_user_model().objects.create_user("other-reviewer")
        self.client.force_login(outsider)
        self.assertNotContains(self.client.get("/feedback/"), data["note"])
        self.assertEqual(self.client.post(url, data).status_code, 404)
        outsider.is_staff = True
        outsider.save(update_fields=["is_staff"])
        self.assertContains(self.client.get("/feedback/"), data["note"])


class DashboardTests(TestCase):
    def test_permissions_counts_and_privacy(self):
        from django.contrib.auth.models import Permission
        from django.utils import timezone
        from .models import LessonFeedback

        reviewer = get_user_model().objects.create_user("reviewer")
        child = Learner.objects.create(parent=reviewer, nickname="PrivateNickname")
        child.assignment_set.create(lesson="keys-v1", retries=2)
        child.assignment_set.create(lesson="keys-v1")
        child.assignment_set.create(lesson="keys-v1", completed=timezone.now(), step=3)
        LessonFeedback.objects.create(parent=reviewer, lesson="keys-v1", kind="change", note="Use larger keys")
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)
        self.client.force_login(reviewer)
        self.assertEqual(self.client.get("/dashboard/").status_code, 403)
        reviewer.user_permissions.add(Permission.objects.get(codename="review_lessons"))
        response = self.client.get("/dashboard/?lesson=keys-v1")
        row, = response.context["rows"]
        self.assertEqual([row[k] for k in ("assigned","started","finished","retries","change")], [3,2,1,None,1])
        self.assertContains(response, "Use larger keys")
        self.assertNotContains(response, "PrivateNickname")
        self.assertNotContains(self.client.get("/dashboard/?flag=worked"), "Use larger keys")
        for i in range(4):
            learner = Learner.objects.create(parent=reviewer, nickname=str(i))
            learner.assignment_set.create(lesson="keys-v1", step=1)
        self.assertEqual(self.client.get("/dashboard/?lesson=keys-v1").context["rows"][0]["retries"], 2)


class FeedbackWorkflowTests(TestCase):
    def setUp(self):
        from .models import LessonFeedback
        User = get_user_model()
        self.parent = User.objects.create_user("writer", email="writer@example.org")
        self.staff = User.objects.create_user("review-team", is_staff=True)
        self.note = LessonFeedback.objects.create(parent=self.parent, lesson="keys-v1", kind="worked")
        self.read = {"action": "read", "feedback": self.note.pk}
        self.reply = {"action": "reply", "feedback": self.note.pk, "reply": "We kept the key hint.",
                      "submission": "22db086f-c868-442e-bb96-2b89ebeed903"}

    def test_opt_in_state_changes_and_repeat_submissions(self):
        from django.core import mail
        self.client.force_login(self.parent)
        self.assertEqual(self.client.post("/dashboard/", self.reply).status_code, 403)
        self.client.post("/feedback/preferences/", {"notify": "on"})
        self.client.force_login(self.staff)
        for data in [self.read, self.read, self.reply, self.reply]:
            self.assertEqual(self.client.post("/dashboard/", data).status_code, 302)
        self.assertEqual([m.to for m in mail.outbox], [[self.parent.email], [self.parent.email]])
        self.assertEqual(self.note.replies.count(), 1)
        self.client.force_login(self.parent)
        self.assertContains(self.client.get("/feedback/"), "We kept the key hint.")
        self.client.post("/feedback/preferences/", {})
        self.client.force_login(self.staff)
        self.client.post("/dashboard/", dict(self.reply, submission="d4df4a2f-d55c-4f8f-b4d1-922218f1bc00"))
        self.assertEqual(len(mail.outbox), 2)

    def test_default_off_reply_marks_read_and_is_private(self):
        from django.core import mail
        self.client.force_login(self.staff)
        self.client.post("/dashboard/", self.reply)
        self.note.refresh_from_db()
        self.assertIsNotNone(self.note.read_at)
        self.assertEqual(len(mail.outbox), 0)
        outsider = get_user_model().objects.create_user("unrelated")
        self.client.force_login(outsider)
        self.assertNotContains(self.client.get("/feedback/"), self.reply["reply"])


class PracticeRoundTests(TestCase):
    def test_rounds_repeat_the_skill_and_keep_catalog_intact(self):
        from copy import deepcopy
        from .practice import build_round, round_count
        original = deepcopy(LESSONS)
        for key, base in LESSONS.items():
            examples = []
            for n in range(min(round_count(key), 24)):
                lesson = build_round(key, n)
                self.assertEqual(lesson["skill"], base["skill"])
                self.assertEqual(len(lesson["items"]), len(base["items"]))
                self.assertEqual(lesson, build_round(key, n))
                for item in lesson["items"]:
                    if item["choices"]:
                        self.assertIn(item["answer"], item["choices"])
                    if lesson["kind"] == "basket":
                        self.assertIn(int(item["answer"]), range(1, 13))
                examples.append(lesson["items"])
            self.assertNotEqual(examples[0], examples[1], key)
            self.assertNotEqual(examples[1], examples[2], key)
        self.assertEqual(LESSONS, original)

    def test_preview_assign_resume_repeat(self):
        from .practice import build_round
        parent = get_user_model().objects.create_user("practice-parent")
        self.client.force_login(parent)
        child = Learner.objects.create(parent=parent, nickname="Sprout")
        key = "market-v1"
        library = f"/children/{child.pk}/library/"
        url = library + key + "/preview/0/?v=17"
        seen = self.client.get(url).context["lesson"]
        self.assertRedirects(self.client.post(url, {"answer":seen["items"][0]["answer"]}),
                             library + key + "/preview/1/?v=17")
        self.client.post(library, {"lesson": key, "variation":17})
        row = child.assignment_set.get()
        self.assertEqual(row.round_snapshot, seen)
        self.client.post(library, {"lesson":key})
        self.assertEqual(child.assignment_set.last().round_snapshot, build_round(key,18))
        self.client.post(f"/children/{child.pk}/",{"action":"play"})
        play_url = f"/play/{row.pk}/"
        self.client.post(play_url, {"step":0,"answer":seen["items"][0]["answer"]})
        for _ in range(2):
            self.assertEqual(self.client.get(play_url).context["item"], seen["items"][1])
