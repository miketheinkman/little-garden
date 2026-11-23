from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Learner


class AssignmentHistoryTests(TestCase):
    def setUp(self):
        parent = get_user_model().objects.create_user("parent")
        self.child = Learner.objects.create(parent=parent, nickname="Fern")
        self.sibling = Learner.objects.create(parent=parent, nickname="Ash")
        self.client.force_login(parent)
        self.history = reverse("assignment_history", args=[self.child.pk])
        self.library = reverse("library", args=[self.child.pk])

    def test_card_uses_latest_full_round_across_versions_and_respects_midnight(self):
        now = datetime(2026, 11, 1, 6, 15, tzinfo=dt_timezone.utc)
        yesterday = now - timedelta(hours=2)
        self.child.assignment_set.create(lesson="keys-v1", completed=yesterday, step=3)
        self.child.assignment_set.create(lesson="keys-v2", completed=now, step=5, skipped=2)
        self.child.assignment_set.create(lesson="keys-v2", removed_at=now)
        with timezone.override("America/Chicago"), patch("django.utils.timezone.now", return_value=now):
            self.assertContains(self.client.get(self.library), "Last completed")
            self.assertContains(self.client.get(self.library), ">yesterday</time>", count=1)
            self.assertNotContains(self.client.get(reverse("library", args=[self.sibling.pk])), "Last completed")
            october = self.client.get(self.history, {"month": "2026-10", "lesson": "keys-v2"})
            self.assertEqual([r.lesson for r in october.context["page"]], ["keys-v1"])
            november = self.client.get(self.history, {"month": "2026-11", "lesson": "keys-v2"})
            self.assertEqual([r.status for r in november.context["page"]], ["Removed", "Finished with skips"])

    def test_history_scopes_access_and_filters_all_statuses(self):
        now = timezone.now()
        for fields in ({"assigned_at": None}, {"step": 1}, {"round_snapshot": None, "retries": 1},
                       {"skipped": 1, "step": 3, "completed": now}, {"completed": now}, {"removed_at": now}):
            self.child.assignment_set.create(lesson="keys-v1", **fields)
        self.sibling.assignment_set.create(lesson="sounds-v1")
        response = self.client.get(self.history)
        page = response.context["page"]
        self.assertEqual(page.paginator.count, 6)
        self.assertIsNone(page[-1].history_date)
        self.assertContains(response, "Date unavailable")
        self.assertEqual(self.client.get(self.history, {"status": "In progress"}).context["page"].paginator.count, 2)
        other = get_user_model().objects.create_user("neighbor")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.history).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.history).status_code, 302)

    def test_repeats_paginate_in_stable_order_with_filters(self):
        now = timezone.now()
        rows = [self.child.assignment_set.create(lesson="keys-v1", step=3, completed=now) for _ in range(22)]
        response = self.client.get(self.history, {"status": "Completed", "lesson": "keys-v2"})
        self.assertContains(response, "Older assignments")
        self.assertContains(response, "status=Completed&amp;lesson=keys-v2&amp;page=2")
        self.assertEqual(list(response.context["page"]), list(reversed(rows[2:])))
        response = self.client.get(self.history, {"page": 2, "lesson": "keys-v2"})
        self.assertEqual(list(response.context["page"]), [rows[1], rows[0]])
