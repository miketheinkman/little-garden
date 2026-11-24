from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .explorations import EXPLORATIONS
from .models import Learner
from .practice import build_round, round_count
from .themes import themed_round


class ExplorationTests(TestCase):
    def setUp(self):
        parent = get_user_model().objects.create_user("test-parent")
        self.child = Learner.objects.create(parent=parent, nickname="Robin", lesson_theme="space")
        self.client.force_login(parent)

    def test_generated_rounds_have_five_solvable_questions(self):
        for key in EXPLORATIONS:
            first = build_round(key, 0)
            self.assertNotEqual(first["items"], build_round(key, 1)["items"], key)
            for variation in range(round_count(key)):
                base = build_round(key, variation)
                lesson = themed_round(key, base, "space", variation)
                self.assertEqual(len(lesson["items"]), 5)
                for item in lesson["items"]:
                    if item["choices"]:
                        self.assertEqual(item["choices"].count(item["answer"]), 1)
                    if lesson["tool"] == "dots":
                        labels = [p["label"] for p in item["dots"]]
                        indexes = [int(x) if x.isdigit() else ord(x) for x in labels]
                        self.assertEqual(indexes, list(range(indexes[0], indexes[0]+len(labels))))
                    elif lesson["tool"] == "money-total":
                        cents = sum(m["cents"] for m in item["handful"])
                        expected = f"${cents/100:.2f}" if cents >= 100 else f"{cents}¢"
                        self.assertEqual(item["answer"], expected)

    def test_saved_envelopes_keep_their_labels_and_direction(self):
        from .templatetags.lesson_cues import trail_dots
        coords = [(12,25), (88,25), (88,76), (12,76), (12,43), (50,62), (75,43)]
        for mirror in (False, True):
            nodes = [dict(x=100-x if mirror else x, y=y, label=label) for label, (x,y) in zip("EFGHIJK", coords)]
            display = trail_dots({"outline": "envelope", "dots": nodes})
            self.assertEqual([dot["label"] for dot in display], list("EFGHIJK"))
            self.assertEqual(display[0]["x"], nodes[0]["x"])
            self.assertEqual(display[0]["x"], display[1]["x"])
            self.assertEqual(display[5]["y"], display[0]["y"])
            self.assertEqual((display[6]["x"], display[6]["y"]), (50,56))

    def test_every_preview_accepts_solution_and_records_nothing(self):
        for key in EXPLORATIONS:
            for step, item in enumerate(build_round(key, 1)["items"]):
                url = reverse("preview", args=[self.child.pk, key, step]) + "?v=1"
                data = {"step": step, "answer": item["answer"]}
                if "dots" in item:
                    data["tool_state"] = item["answer"]
                if "pieces" in item:
                    data["tool_state"] = ",".join(str(p["bin"]) for p in item["pieces"])
                if step == 0:
                    self.assertContains(self.client.get(url), item["prompt"], html=True)
                self.assertEqual(self.client.post(url, data).status_code, 302, (key, step))
        self.assertFalse(self.child.assignment_set.exists())

    def test_assigned_dot_trail_requires_order_and_keeps_first_try_score(self):
        key = "letter-dots-v1"
        self.client.post(reverse("library", args=[self.child.pk]), {"lesson": key, "variation": 3})
        row = self.child.assignment_set.get()
        self.client.post(reverse("manage", args=[self.child.pk]), {"action": "play"})
        url = reverse("play", args=[row.pk])
        items = row.round_snapshot["items"]
        self.assertContains(self.client.post(url, {"step": 0, "answer": items[0]["answer"], "tool_state":"1,0"}), "try again")
        for i, item in enumerate(items):
            self.assertEqual(self.client.post(url, {"step":i, "tool_state":item["answer"]}).status_code, 302)
        row.refresh_from_db()
        self.assertIsNotNone(row.completed)
        self.assertEqual(row.retries, 1)
        self.assertEqual(list(row.samples.order_by("step").values_list("score", flat=True)), [0,100,100,100,100])
