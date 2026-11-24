import uuid
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .assessment import evidence_method
from .assignments import assign_lesson
from .models import Learner, Purpose
from .practice import CURRENT_LESSONS
from .reviews import coverage
from .scheduling import release_due
from .tests import correct_submission


class ReviewCoverageTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("review-parent")
        self.child = Learner.objects.create(parent=self.parent, nickname="Ash")
        self.client.force_login(self.parent)
        self.url = reverse("placement_reviews", args=[self.child.pk])
        self.player = Client()
        self.player.force_login(self.parent)
        self.player.post(reverse("manage", args=[self.child.pk]), {"action":"play"})

    def test_every_current_lesson_can_be_placed_and_reviewed_in_the_player(self):
        first_review = timezone.localdate()+timedelta(days=28)
        planner = reverse("planner", args=[self.child.pk])
        for key, lesson in CURRENT_LESSONS.items():
            with self.subTest(key=key):
                self.client.post(self.url, {"lesson":key, "purpose":"placement"})
                row = self.child.assignment_set.get(lesson=key, completed=None)
                self.assertEqual(row.purpose, Purpose.PLACEMENT)
                url = reverse("play", args=[row.pk])
                self.assertEqual(self.player.get(url).status_code, 200)
                for step,item in enumerate(lesson["items"]):
                    response = self.player.post(url, dict(correct_submission(item), step=step))
                    self.assertEqual(response.status_code, 302)
                row.refresh_from_db()
                self.assertIsNotNone(row.completed)
                self.assertEqual(row.samples.count(), 0 if evidence_method(lesson) == "observation" else len(lesson["items"]))
                if evidence_method(lesson) == "observation":
                    self.child.observation_set.create(assignment=row, observed_on=timezone.localdate(), text="Tried independently.")
                response = self.client.post(f"{planner}?lesson={key}&v=17", {"lesson":key, "purpose":"review",
                                            "start":first_review, "repeat":"fourweeks", "submission":uuid.uuid4()})
                self.assertEqual(response.status_code, 302)
        release_due(self.child, first_review)
        reviews = self.child.assignment_set.filter(purpose=Purpose.REVIEW).order_by("pk")
        self.assertCountEqual(reviews.values_list("lesson", flat=True), CURRENT_LESSONS)
        for row in reviews:
            with self.subTest(scheduled_review=row.lesson):
                self.assertEqual((row.variation,row.scheduled_for),(17,first_review))
                url = reverse("play", args=[row.pk])
                self.player.get(url)
                for step,item in enumerate(row.round_snapshot["items"]):
                    self.assertEqual(self.player.post(url,dict(correct_submission(item),step=step)).status_code,302)
                row.refresh_from_db()
                self.assertIsNotNone(row.completed)
        groups = coverage(self.child)
        self.assertEqual(sum(g["covered"] for g in groups), len(CURRENT_LESSONS))
        self.assertEqual({g["strand"] for g in groups}, {lesson["strand"] for lesson in CURRENT_LESSONS.values()})

    def test_incomplete_assisted_and_observed_checks(self):
        for key, mode in (("add-groups-v1","skip"), ("light-paths-v1","hint"), ("lines-v1","observe")):
            row = assign_lesson(self.child, key, purpose=Purpose.REVIEW)
            url = reverse("play", args=[row.pk])
            for step, item in enumerate(row.round_snapshot["items"]):
                data = correct_submission(item)
                if mode == "hint" and step == 0:
                    self.player.post(url, dict(data, action="hint",step=step))
                if mode == "skip" and step == 0:
                    self.assertEqual(self.player.post(url, {"step":0}).status_code,302)
                    self.assertFalse(row.samples.exists())
                    data = {"action":"skip"}
                self.player.post(url, dict(data,step=step))
            result = next(r for g in coverage(self.child) for r in g["rows"] if r["key"]==key)
            self.assertTrue(result["partial"])
            self.assertIsNone(result["last"])
            if mode == "observe":
                self.assertFalse(row.samples.exists())

    def test_first_response_and_duplicate_submission(self):
        key = "sort-baskets-v1"
        for _ in range(2):
            self.client.post(self.url, {"purpose":"placement","lesson":key})
        row = self.child.assignment_set.get()
        url = reverse("play", args=[row.pk])
        self.player.post(url, {"step":0, "tool_state":"1"})
        self.assertFalse(row.samples.exists())
        fields = ",".join("1" for _ in row.round_snapshot["items"][0]["pieces"])
        for _ in range(2):
            self.player.post(url, {"step":0,"tool_state":fields})
        row.refresh_from_db()
        self.assertEqual((row.step, row.samples.get().score),(1,0))

    @patch("django.utils.timezone.localdate", return_value=date(2027,1,1))
    def test_four_week_review_across_months_catchup_and_end(self, _):
        start = date(2027,1,31)
        key = "money-total-v1"
        planner = reverse("planner", args=[self.child.pk]) + f"?purpose=review&lesson={key}"
        self.client.post(planner, {"purpose":"review","start":start,"repeat":"fourweeks","lesson":key,
                                  "end":start+timedelta(days=84),"submission":uuid.uuid4()})
        plan = self.child.lessonplan_set.get()
        feb = self.client.get(reverse("family_calendar"), {"day":"2027-02-28"})
        self.assertEqual(feb.context["month_count"],1)
        self.assertEqual(feb.context["selected_entries"][0]["purpose"],"Skill review")
        release_due(self.child, start+timedelta(days=61))
        row = plan.assignment_set.get()
        self.assertEqual((row.purpose,row.scheduled_for),(Purpose.REVIEW,start+timedelta(days=56)))
        plan.refresh_from_db()
        self.assertEqual(plan.next_on,start+timedelta(days=84))
        release_due(self.child, start+timedelta(days=100))
        self.assertEqual(plan.assignment_set.count(),1)
        plan.refresh_from_db()
        self.assertIsNone(plan.next_on)

    def test_private_and_validated(self):
        other = Learner.objects.create(parent=get_user_model().objects.create_user("elsewhere"),nickname="Fern")
        self.assertEqual(self.client.get(reverse("placement_reviews",args=[other.pk])).status_code,404)
        self.assertEqual(self.client.post(self.url, {"purpose":"review","lesson":"missing"}).status_code,404)
        self.assertEqual(self.client.get(self.url, {"status":"unknown"}).status_code,404)
        self.assertEqual(self.player.get(self.url).status_code,302)

    def test_due_after_eight_full_independent_rounds_and_not_for_sibling_skills(self):
        when = timezone.now() - timedelta(days=14)
        key = "money-id-v1"
        checked = self.child.assignment_set.create(lesson=key, step=1, purpose=Purpose.PLACEMENT, completed=when)
        checked.samples.create(step=0, strand="Money sense", level=2, score=0)

        def status(key):
            return next(r["status"] for g in coverage(self.child) for r in g["rows"] if r["key"] == key)

        for i in range(8):
            row = self.child.assignment_set.create(lesson="money-total-v1", completed=when+timedelta(days=i+1),
                                                   step=1, skipped=int(i==7))
            if not row.skipped:
                row.samples.create(step=0,strand="Money sense", level=3, score=100)
        self.assertEqual(status(key), "Checked")
        row.skipped = 0
        row.save()
        row.samples.create(step=0,strand="Money sense", level=3, score=0)
        self.assertEqual(status(key), "Review due")
        self.assertEqual(status("money-total-v1"), "Awaiting baseline")

    def test_preview_preserves_first_try_mode_and_selected_round(self):
        key = "money-total-v1"
        preview = reverse("preview", args=[self.child.pk, key, 0])
        url = preview+"?v=14&purpose=review"
        result = self.client.post(url, {"answer":"wrong"}, HTTP_ACCEPT="application/json").json()
        self.assertEqual(result["result"], "advance")
        self.assertIn("purpose=review", result["next"])
        self.assertFalse(self.child.assignment_set.exists())
        self.client.post(reverse("library",args=[self.child.pk]), {"lesson":key,"variation":14,"purpose":"review"})
        row = self.child.assignment_set.get()
        self.assertEqual((row.purpose,row.variation),(Purpose.REVIEW,14))
        self.assertEqual(self.client.get(preview+"?purpose=unknown").status_code,404)

    def test_repeating_placement_turns_into_review_after_first_release(self):
        start = timezone.localdate()+timedelta(days=3)
        plan = self.child.lessonplan_set.create(lesson="sort-baskets-v1", purpose=Purpose.PLACEMENT,
                                                next_on=start, repeat="fourweeks")
        calendar = reverse("family_calendar")
        self.assertEqual(self.client.get(calendar, {"day":start}).context["selected_entries"][0]["purpose"], "Initial placement")
        second = start+timedelta(days=28)
        self.assertEqual(self.client.get(calendar, {"day":second}).context["selected_entries"][0]["purpose"], "Skill review")
        release_due(self.child,start)
        first = plan.assignment_set.get()
        self.assertEqual(first.purpose,Purpose.PLACEMENT)
        first.completed=timezone.now()
        first.save()
        release_due(self.child,second)
        self.assertEqual(plan.assignment_set.get(scheduled_for=second).purpose,Purpose.REVIEW)

    def test_guided_practice_does_not_inflate_placement(self):
        from .progression import Progress
        key = "arrow-maze-v1"
        row = assign_lesson(self.child,key)
        self.player.post(reverse("play",args=[row.pk]),dict(correct_submission(row.round_snapshot["items"][0]),step=0))
        self.assertFalse(row.samples.exists())
        row.samples.create(step=0,strand="Keyboard use",level=2,score=100)
        self.assertNotIn("Keyboard use",Progress(self.child).estimates)
