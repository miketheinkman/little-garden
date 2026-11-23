from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Learner, SkillSample
from .operations import pilot_usage, server_health


class TechnicalDashboardTests(TestCase):
    def test_staff_access_and_unavailable_health(self):
        url = reverse("technical_dashboard")
        self.assertEqual(self.client.get(url).status_code, 302)
        reviewer = get_user_model().objects.create_user("reviewer")
        self.client.force_login(reviewer)
        self.assertEqual(self.client.get(url).status_code, 403)
        reviewer.user_permissions.add(Permission.objects.get(codename="review_lessons"))
        self.assertContains(self.client.get(reverse("dashboard")), url)
        with patch("pilot.operations.Path.open", side_effect=OSError), patch("pilot.operations.shutil.disk_usage", side_effect=OSError):
            response = self.client.get(url)
        self.assertContains(response, "Unavailable", count=4)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.context["usage"]["returning"], 0)
        self.assertEqual(response.context["usage"]["week_total"], 0)

    def test_host_reports_cpu_delta(self):
        with patch("pilot.operations.cpu_ticks", side_effect=[(125, 20), (225, 85)]):
            self.assertEqual(server_health()["cpu"], 35)

    def test_usage_windows_siblings_and_participation(self):
        now = timezone.now()
        users = get_user_model().objects
        family = users.create_user("family")
        fern = Learner.objects.create(parent=family, nickname="Fern")
        iris = Learner.objects.create(parent=family, nickname="Iris")
        ash = Learner.objects.create(parent=users.create_user("second"), nickname="Ash")
        weeks_ago = now - timedelta(days=32)
        early = now - timedelta(days=12)
        row = fern.assignment_set.create(lesson="keys-v1", completed=early, step=3)
        first = SkillSample.objects.create(assignment=row, step=0, strand="Keys", level=1, score=100)
        SkillSample.objects.filter(pk=first.pk).update(measured=early)
        iris.assignment_set.create(lesson="keys-v2", completed=now, step=5)
        fern.assignment_set.create(lesson="keys-v1", completed=now, step=3, skipped=1)
        ash.assignment_set.create(lesson="keys-v1", completed=weeks_ago, step=3)
        row = ash.assignment_set.create(lesson="keys-v1", step=1)
        latest = SkillSample.objects.create(assignment=row, step=0, strand="Keys", level=1, score=100)
        SkillSample.objects.filter(pk=latest.pk).update(measured=now)
        users.filter(pk=family.pk).update(date_joined=weeks_ago)
        users.filter(pk=ash.parent_id).update(date_joined=early)
        for key, expiry in (("idle", now+timedelta(days=2)), ("expired", now)):
            Session.objects.create(session_key=key, session_data="", expire_date=expiry)
        usage = pilot_usage(now)
        self.assertEqual((usage["accounts"], usage["learners"], usage["sessions"]), ({"registered": 2, "new": 1}, 3, 1))
        self.assertEqual((usage["active"], usage["returning"]), (2, 1))
        self.assertEqual(usage["totals"], {"completed": 3, "with_skips": 1})
        self.assertEqual(usage["week_total"], 1)
        self.assertEqual(len(usage["week"]), 7)
        self.assertEqual(usage["week"][-1], (timezone.localdate(now), 1, 100))
