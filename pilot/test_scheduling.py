import uuid
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Learner, LessonPlan
from .scheduling import release_due


class PlannerTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("planner")
        self.child = Learner.objects.create(parent=self.parent, nickname="Clover")
        self.client.force_login(self.parent)
        self.url = reverse("planner", args=[self.child.pk])
        self.today = timezone.localdate()

    def plan(self, key="ten-v1", **changes):
        data = dict(lesson=key, start=self.today + timedelta(days=1), repeat="once", submission=str(uuid.uuid4()))
        data.update(changes)
        return data

    def test_future_release_saved_round_and_replayed_submission(self):
        data = self.plan("my-letters-v1")
        url = self.url + "?lesson=my-letters-v1&v=17&letters=QXZ"
        for _ in range(2):
            self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.child.lessonplan_set.count(), 1)
        self.client.post(reverse("manage", args=[self.child.pk]), {"action":"play"})
        self.assertFalse(self.client.get("/").context["queue"])
        self.assertTrue(self.client.get("/").context["suggestions"])
        with patch("django.utils.timezone.localdate", return_value=data["start"]):
            queue = self.client.get("/").context["queue"]
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0].scheduled_for, data["start"])
            self.assertEqual(queue[0].round_snapshot["letters"], "QXZ")
            self.assertEqual(queue[0].variation, 17)
            self.assertEqual(self.client.get("/").context["queue"][0].pk, queue[0].pk)
        self.assertIsNone(self.child.lessonplan_set.get().next_on)

    def test_weekly_catch_up_fresh_round_end_and_unfinished_session(self):
        monday = date(2027, 1, 4)
        plan = self.child.lessonplan_set.create(lesson="ten-v1", repeat="weekly", weekdays="03", next_on=monday,
                                                first_variation=17, ends_on=monday+timedelta(days=10))
        release_due(self.child, monday + timedelta(days=4))
        first = plan.assignment_set.get()
        self.assertEqual(first.scheduled_for, monday+timedelta(days=3))
        self.assertEqual(first.variation, 17)
        release_due(self.child, monday + timedelta(days=7))
        self.assertEqual(plan.assignment_set.count(), 1)
        first.completed = timezone.now()
        first.save()
        release_due(self.child, monday + timedelta(days=30))
        second = plan.assignment_set.last()
        self.assertNotEqual(second.variation, first.variation)
        self.assertEqual(second.scheduled_for, plan.ends_on)
        plan.refresh_from_db()
        self.assertIsNone(plan.next_on)
        release_due(self.child, monday + timedelta(days=40))
        self.assertEqual(plan.assignment_set.count(), 2)

    def test_validation_edit_cancel_and_family_ownership(self):
        bad = self.plan(start=self.today - timedelta(days=1), repeat="weekly")
        result = self.client.post(self.url, bad)
        self.assertFormError(result.context["form"], "weekdays", "Choose at least one practice day.")
        self.assertFormError(result.context["form"], "start", "Choose today or a future date.")
        self.assertFalse(self.child.lessonplan_set.exists())
        monday = self.today + timedelta(days=7-self.today.weekday())
        self.client.post(self.url, self.plan(start=monday, repeat="weekdays"))
        plan = self.child.lessonplan_set.get()
        edit = self.url + f"?edit={plan.pk}"
        self.client.post(edit, self.plan(start=monday, repeat="weekly", weekdays=["3"], end=monday))
        plan.refresh_from_db()
        self.assertEqual(plan.repeat, "weekdays")
        self.client.post(edit, self.plan(start=monday, repeat="weekly", weekdays=["3"], end=monday+timedelta(days=7)))
        plan.refresh_from_db()
        self.assertEqual(plan.next_on, monday+timedelta(days=3))
        intruder = get_user_model().objects.create_user("other-family")
        self.client.force_login(intruder)
        self.assertEqual(self.client.get(edit).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"action":"cancel","plan":plan.pk}).status_code, 404)
        self.client.force_login(self.parent)
        self.client.post(self.url, {"action":"cancel","plan":plan.pk})
        release_due(self.child, monday+timedelta(days=10))
        self.assertFalse(self.child.assignment_set.exists())

    def test_daily_release_before_stale_suggestion_and_cancel_leaves_queue(self):
        self.client.post(self.url, self.plan(start=self.today + timedelta(days=1), repeat="daily"))
        self.client.post(reverse("manage", args=[self.child.pk]), {"action":"play"})
        suggestion = self.client.get("/").context["suggestions"][0]["key"]
        with patch("django.utils.timezone.localdate", return_value=self.today+timedelta(days=1)):
            self.client.post(reverse("start_suggestion"), {"lesson":suggestion})
            self.assertEqual(self.child.assignment_set.get().lesson, "ten-v1")
            self.assertFalse(self.client.get("/").context["suggestions"])
            self.client.force_login(self.parent)
            plan = self.child.lessonplan_set.get()
            self.client.post(self.url, {"action":"cancel","plan":plan.pk})
            self.assertIsNone(self.child.assignment_set.get().removed_at)


class FamilyCalendarTests(TestCase):
    def setUp(self):
        parent = get_user_model().objects.create_user("calendar-parent")
        self.client.force_login(parent)
        self.fern = Learner.objects.create(parent=parent, nickname="Fern")
        self.ash = Learner.objects.create(parent=parent, nickname="Ash")
        stranger = get_user_model().objects.create_user("calendar-neighbor")
        self.other = Learner.objects.create(parent=stranger, nickname="Other")
        self.url = reverse("family_calendar")

    @patch("django.utils.timezone.localdate", return_value=date(2028, 2, 1))
    def test_family_month_projection_and_filter(self, _):
        start, leap = date(2028, 2, 1), date(2028, 2, 29)
        self.fern.lessonplan_set.create(lesson="ten-v1", repeat="weekly", weekdays="1",
                                        next_on=start, ends_on=leap)
        self.ash.lessonplan_set.create(lesson="five-v1", repeat="once", next_on=leap)
        self.other.lessonplan_set.create(lesson="five-v1", repeat="daily", next_on=start)
        response = self.client.get(self.url, {"day":leap})
        self.assertEqual(response.context["month_count"], 6)
        self.assertEqual([item["child"] for item in response.context["selected_entries"]], [self.ash,self.fern])
        self.assertEqual(response.context["following"], date(2028,3,1))
        self.assertEqual(response.context["previous"], date(2028,1,1))
        filtered = self.client.get(self.url, {"day":start, "child":self.fern.pk})
        self.assertEqual(filtered.context["month_count"], 5)
        self.assertEqual(filtered.context["selected_entries"][0]["status"], "In queue")
        self.assertEqual(self.fern.assignment_set.count(), 1)
        self.assertEqual(self.client.get(self.url, {"day":"2028-03-01"}).context["month_count"], 0)
        self.assertEqual(self.client.get(self.url, {"child": self.other.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"day":"invalid"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_past_calendar_and_saving_from_filtered_date(self):
        past = timezone.localdate()-timedelta(days=6)
        for changes in ({"completed":timezone.now()}, {"removed_at":timezone.now()}):
            self.fern.assignment_set.create(lesson="ten-v1", scheduled_for=past, **changes)
        self.fern.assignment_set.create(lesson="five-v1")
        day = self.client.get(self.url, {"day":past}).context["selected_entries"]
        self.assertEqual([item["status"] for item in day], ["Completed"])
        future = timezone.localdate()+timedelta(days=14)
        planner = reverse("planner", args=[self.fern.pk]) + f"?day={future}&calendar=child"
        self.assertEqual(self.client.get(planner).context["form"].initial["start"], future)
        response = self.client.post(planner, {"lesson":"ten-v1", "start":future, "repeat":"once", "submission":uuid.uuid4()})
        self.assertEqual(response.url, f"{self.url}?day={future}&child={self.fern.pk}#day-plan")
        self.assertEqual(self.client.get(response.url).context["selected_entries"][0]["status"], "Planned")
