import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .discovery import PATCH, discovery_round, letter_selection
from .models import Learner, SkillSample
from .practice import CURRENT_LESSONS, ORIGINALS, build_round, round_count
from .question_sets import identity
from .themes import THEMES, themed_round


class QuestionSetTests(SimpleTestCase):
    def test_distinct_after_applying_the_childs_theme(self):
        for key in CURRENT_LESSONS:
            group = key.rsplit("-v", 1)[0]
            for variation in (0, 1, round_count(key) // 2, round_count(key) - 1):
                base = build_round(key, variation)
                for theme in THEMES:
                    items = themed_round(key, base, theme, variation)["items"]
                    questions = {identity(group, item, i) for i, item in enumerate(items)}
                    self.assertEqual(len(items), len(questions), (key, variation, theme))

    def test_small_custom_sets_and_reversed_arithmetic(self):
        for text in ("Q", "Q z Q", "aBcDeFg"):
            selected = letter_selection(text)
            items = discovery_round(PATCH, 12, selected)["items"]
            self.assertCountEqual([item["answer"] for item in items], selected)
        def arithmetic(equation):
            return identity("arithmetic", {"answer": "5", "equation": equation}, 0)
        self.assertEqual(arithmetic("2 + 3"), arithmetic("3 + 2"))
        self.assertNotEqual(arithmetic("8 − 3"), arithmetic("3 − 8"))


class WeeklyRecordTests(TestCase):
    def setUp(self):
        parent = get_user_model().objects.create_user("record-parent")
        other = get_user_model().objects.create_user("other-parent")
        self.client.force_login(parent)
        self.child = Learner.objects.create(parent=parent, nickname="Fern")
        self.other = Learner.objects.create(parent=other, nickname="Ash")
        self.url = reverse("weekly_record", args=[self.child.pk])
        self.today = timezone.localdate()
        self.data = {"observed_on": self.today, "text": "Recognized the key.",
                     "submission": str(uuid.uuid4())}

    def test_private_notes_from_lesson_history(self):
        row = self.child.assignment_set.create(lesson="keys-v2", position=1)
        other_row = self.other.assignment_set.create(lesson="keys-v2", position=1)
        note_url = f"{self.url}?assignment={row.pk}"
        for _ in range(2):
            self.assertEqual(self.client.post(note_url, self.data).status_code, 302)
        note = self.child.observation_set.get()
        self.assertEqual(note.assignment_id, row.pk)
        self.assertContains(self.client.get(self.url), self.data["text"])
        self.assertNotContains(self.client.get(self.url, {"week":self.today-timedelta(days=7)}), self.data["text"])
        self.assertEqual(self.client.post(f"{self.url}?assignment={other_row.pk}", self.data).status_code, 404)
        self.assertEqual(self.client.get(reverse("weekly_record", args=[self.other.pk])).status_code, 404)
        self.client.post(f"{self.url}?edit={note.pk}", dict(self.data, text="Found it independently."))
        self.assertContains(self.client.get(self.url), "Found it independently.")
        self.client.post(self.url, {"action":"delete", "note":note.pk})
        self.assertFalse(self.child.observation_set.exists())
        self.assertContains(self.client.post(self.url, dict(self.data, observed_on=self.today+timedelta(days=1))),
                            "Choose today or an earlier observation date.")
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_report_counts_only_practice_in_the_week(self):
        row = self.child.assignment_set.create(lesson="keys-v2", position=1)
        for step, score, help_flag in ((0,100,0), (1,0,0), (2,100,1), (3,100,0)):
            sample = SkillSample.objects.create(assignment=row, step=step, strand="Keyboard", level=1,
                                               score=score, puzzle_help=help_flag)
        SkillSample.objects.filter(pk=sample.pk).update(measured=timezone.now()-timedelta(days=9))
        report = self.client.get(self.url)
        self.assertContains(report, "2 scored steps averaging 50%")
        self.assertContains(report, "1 puzzle solved with help")

    def test_unopened_queue_uses_new_set_and_started_round_resumes(self):
        old = ORIGINALS["keys-v2"]
        first = self.child.assignment_set.create(lesson="keys-v2", position=1, round_snapshot=old)
        started = self.child.assignment_set.create(lesson="keys-v2", position=2, step=3,
                                                   round_snapshot=dict(old, _opened_theme="garden"))
        self.client.post(f"/children/{self.child.pk}/", {"action":"play"})
        items = self.client.get(reverse("play", args=[first.pk])).context["lesson"]["items"]
        self.assertEqual(len({item["answer"] for item in items}), 5)
        response = self.client.get(reverse("play", args=[started.pk]))
        self.assertEqual(response.context["item"], old["items"][3])
