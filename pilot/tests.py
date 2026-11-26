from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import Assignment, Learner
from .views import LESSONS


def correct_submission(item):
    data = {"answer": item["answer"], "pixels": "0"*16+"1"+"0"*751}
    if "dots" in item:
        data["tool_state"] = item["answer"]
    if "pieces" in item:
        data["tool_state"] = ",".join(str(p["bin"]) for p in item["pieces"])
    if "recipes" in item:
        recipe = next(r for r in item["recipes"] if r["result"]["name"] == item["answer"])
        data["tool_state"] = ",".join(str(i) for i, pot in enumerate(item["paints"])
                                      if pot["name"] in (recipe["first"], recipe["second"]))
    if "deck" in item:
        pairs = sorted(range(len(item["deck"])), key=lambda i: item["deck"][i]["pair"])
        data["tool_state"] = ",".join(map(str, pairs))
    if "blocks" in item:
        from itertools import combinations
        ids = range(len(item["blocks"]))
        solution = next(ix for n in (1, 2) for ix in combinations(ids, n)
                        if sum(item["blocks"][i]["weight"] for i in ix) == item["target"])
        data["tool_state"] = ",".join(map(str, solution))
    if "board" in item:
        from .test_puzzles import winning_moves
        data["moves"] = "".join(map(str, winning_moves(item["board"])[0]))
    return data


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

    def test_puzzle_experiment_and_assistance(self):
        from .progression import Progress
        self.client.post(self.manage, {"action": "assign", "lesson": "water-works-v1"})
        row = Assignment.objects.get()
        url = f"/play/{row.pk}/"
        self.client.post(self.manage, {"action": "play"})
        for action in ("run", "hint", "parent"):
            self.assertEqual(self.client.post(url, {"step": 0, "moves": "0", "action": action}).status_code, 200)
        self.assertFalse(row.samples.exists())
        row.refresh_from_db()
        self.assertEqual((row.retries, row.step, row.puzzle_help), (0, 0, 3))
        self.assertContains(self.client.post(url, {"step": 0, "answer": "correct"}), "try again")
        self.client.post(url, {"step": 0, "moves": "1"})
        row.refresh_from_db()
        self.assertEqual((row.step, row.puzzle_help, row.samples.get().puzzle_help), (1, 0, 3))
        progress = Progress(self.child)
        self.assertEqual(progress.timeline()[0]["help_counts"], [0, 0, 0, 1])
        self.assertNotIn("Causal reasoning", progress.estimates)
        self.client.post(url, {"step": 1, "moves": "2"})
        self.assertEqual(row.samples.get(step=1).puzzle_help, 0)
        self.assertIn("Causal reasoning", Progress(self.child).estimates)

    def test_appearance_is_per_child_validated_and_resettable(self):
        response = self.client.post(self.manage, {"action": "appearance", "accent": "#ffee11",
                                                 "font": "mono", "use_accent": "on"})
        self.assertEqual(response.status_code, 302)
        self.child.refresh_from_db()
        self.assertEqual(self.child.appearance, {"accent": "#ffee11", "ink": "#000000", "font": "mono"})
        self.assertEqual(self.sibling.appearance["accent"], "")
        response = self.client.post(self.manage, {"action": "appearance", "accent": "url(no)",
                                                 "font": "mono", "use_accent": "on"})
        self.assertEqual(response.status_code, 400)
        self.client.post(self.manage, {"action": "reset-appearance"})
        self.child.refresh_from_db()
        self.assertEqual((self.child.font, self.child.accent), ("default", ""))

    def test_parent_letter_selection_survives_preview_and_assignment(self):
        key = "my-letters-v1"
        library = self.manage + "library/"
        url = library + key + "/preview/6/?v=2&letters=abcdefg"
        preview = self.client.get(url)
        self.assertContains(preview, "Step 7 of 7")
        answer = preview.context["item"]["answer"]
        self.assertIn("letters=ABCDEFG", self.client.post(url, {"answer": answer})["Location"])
        self.assertEqual(self.client.post(library, {"lesson": key, "letters": "12"}).status_code, 400)
        self.assertFalse(self.child.assignment_set.exists())
        self.client.post(library, {"lesson": key, "letters": "a, b, b, c d e f g", "variation": 2})
        row = self.child.assignment_set.get()
        self.assertEqual(row.round_snapshot["items"], preview.context["lesson"]["items"])
        self.assertEqual({i["answer"] for i in row.round_snapshot["items"]}, set("ABCDEFG"))

    def test_paint_recipes_are_solvable_in_either_order(self):
        from .paint import mixture_matches, paint_lesson
        for variation in range(32):
            lesson = paint_lesson("mix-paint-v1", variation)
            self.assertEqual(len({item["answer"] for item in lesson["items"]}), 5)
            for item in lesson["items"]:
                recipe = next(r for r in item["recipes"] if r["result"]["name"] == item["answer"])
                names = [pot["name"] for pot in item["paints"]]
                a, b = names.index(recipe["first"]), names.index(recipe["second"])
                for pair in (f"{a},{b}", f"{b},{a}"):
                    self.assertTrue(mixture_matches(item, pair))
                for invalid in ("", "0", "0,0", "1,2,3", "-1,0", "0,99"):
                    self.assertFalse(mixture_matches(item, invalid))

    def test_table_games_validate_real_pairs_and_weights(self):
        memory = self.child.assignment_set.create(lesson="sound-memory-v1")
        balance = self.child.assignment_set.create(lesson="seesaw-v1")
        self.client.post(self.manage, {"action": "play"})
        def submit(row, state):
            return self.client.post(f"/play/{row.pk}/", {"step": 0, "tool_state": state},
                                    HTTP_ACCEPT="application/json").json()["result"]
        deck = LESSONS[memory.lesson]["items"][0]["deck"]
        order = sorted(range(len(deck)), key=lambda i: deck[i]["pair"])
        for state in ("", "99", "0,0,0,0", ",".join(map(str, order[::2] + order[1::2]))):
            self.assertEqual(submit(memory, state), "retry")
        self.assertEqual(submit(memory, ",".join(map(str, order))), "correct")
        self.assertFalse(memory.samples.exists())
        item = LESSONS[balance.lesson]["items"][0]
        ix = next(i for i, b in enumerate(item["blocks"]) if b["weight"] == item["target"])
        self.assertEqual(submit(balance, str(ix)), "correct")
        self.assertEqual(balance.samples.get().score, 100)

    def test_animation_follows_saved_outcome(self):
        keys = self.child.assignment_set.create(lesson="keys-v1")
        checkin = self.child.assignment_set.create(lesson="number-check-v1")
        guided = self.child.assignment_set.create(lesson="beans-v1")
        self.client.post(self.manage, {"action": "play"})

        def submit(row, answer, step=0):
            return self.client.post(f"/play/{row.pk}/", {"answer": answer, "step": step},
                                    HTTP_ACCEPT="application/json").json()

        self.assertEqual(submit(keys, "X"), {"result": "retry"})
        self.assertEqual(submit(keys, "S")["result"], "correct")
        self.assertEqual(keys.samples.get(step=0).score, 0)
        self.assertEqual(submit(checkin, "2")["result"], "advance")
        self.assertEqual(submit(guided, "We tried it"), {"result": "finished", "next": "/"})
        self.client.force_login(self.parent)
        before = Assignment.objects.count()
        url = f"{self.manage}library/keys-v1/preview/0/"
        for answer, expected in (("X", "retry"), ("S", "correct")):
            self.assertEqual(self.client.post(url, {"answer": answer},
                             HTTP_ACCEPT="application/json").json()["result"], expected)
        self.assertEqual(Assignment.objects.count(), before)

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
        from .practice import CURRENT_LESSONS
        for key in CURRENT_LESSONS:
            self.client.post(self.manage, {"action": "assign", "lesson": key})
        last = self.child.assignment_set.last()
        self.client.post(self.manage, {"action": "first", "row": last.pk})
        self.assertEqual(self.child.assignment_set.first(), last)
        self.client.post(self.manage, {"action": "play"})
        for row in self.child.assignment_set.all():
            response = self.client.get(f"/play/{row.pk}/")
            self.assertContains(response, LESSONS[row.lesson]["items"][0]["prompt"], html=True)

    def test_filtered_bulk_add_skips_active_versions_and_reopens_removed_lessons(self):
        from .practice import CURRENT_LESSONS
        url = self.manage + "library/?category=Keyboard+%26+mouse&participation=Independent"
        legacy = self.child.assignment_set.create(lesson="keys-v1", step=1)
        matching = [key for key, lesson in CURRENT_LESSONS.items() if lesson["category"] == "Keyboard & mouse"]
        self.assertNotContains(self.client.get(url), 'data-lesson="keys-v2"')
        for _ in range(2):
            response = self.client.post(url, {"action": "all"}, HTTP_ACCEPT="application/json")
            self.assertEqual(set(response.json()["active"]), set(matching))
        self.assertEqual(list(self.child.assignment_set.values_list("lesson", flat=True)),
                         ["keys-v1"] + [key for key in matching if key != "keys-v2"])
        self.assertFalse(self.sibling.assignment_set.exists())
        self.client.post(self.manage, {"action": "remove", "row": legacy.pk})
        self.assertContains(self.client.get(url), 'data-lesson="keys-v2"')
        self.client.post(self.manage + "library/", {"action": "all"})
        self.assertEqual(self.child.assignment_set.filter(removed_at=None).count(), len(CURRENT_LESSONS))


    def test_tier_and_fit_filters_use_the_selected_child_for_bulk_add(self):
        from django.utils import timezone
        from urllib.parse import urlencode
        row = self.child.assignment_set.create(lesson="count1-v1", completed=timezone.now())
        row.samples.create(step=0, strand="Number sense", level=1, score=100)
        filters = {"category": "Numbers & patterns", "participation": "Independent", "tier": "4", "fit": "Above level"}
        url = self.manage + "library/?" + urlencode(filters)
        response = self.client.get(url)
        matches = {key for entries in response.context["groups"].values() for key, *_ in entries}
        self.assertEqual(matches, {"ten-v1", "market-v1", "coins-v1", "clock-v1"})
        sibling_url = url.replace(self.manage, f"/children/{self.sibling.pk}/")
        self.assertContains(self.client.get(sibling_url), "No lessons match these filters")
        self.assertContains(self.client.get(sibling_url.replace("Above+level", "Placement+pending")), 'data-lesson="ten-v1"')
        self.client.post(url, {"action": "all"})
        self.assertEqual(set(self.child.assignment_set.filter(completed=None).values_list("lesson", flat=True)), matches)
        checks = self.client.get(self.manage + "library/?tier=checkin&fit=Placement+check-in")
        self.assertEqual(checks.context["available"], 3)


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

    def test_catalog_return_without_scripts_and_from_direct_preview(self):
        from urllib.parse import parse_qs, urlsplit

        path = self.library + "my-letters-v1/preview/0/"
        filters = {"category": "Keyboard & mouse", "fit": "On level", "tier": "2"}
        page = self.client.get(path, {"catalog": "1", "letters": "abc", **filters})
        back = urlsplit(page.context["library_url"])
        self.assertEqual((back.path, back.fragment), (self.library, "lesson-my-letters-v1"))
        self.assertEqual(parse_qs(back.query), {key: [value] for key, value in filters.items()})
        for key, value in {"catalog": "1", **filters}.items():
            self.assertContains(page, f'<input type="hidden" name="{key}" value="{value}">', html=True)
        self.assertEqual(self.client.get(path).context["library_url"], self.library)

    def test_previews_can_be_completed_without_learner_records(self):
        for key, lesson in LESSONS.items():
            for step, item in enumerate(lesson["items"]):
                url = f"{self.library}{key}/preview/{step}/"
                self.assertContains(self.client.get(url), item["prompt"], html=True)
                data = correct_submission(item)
                response = self.client.post(url, data, follow=True)
            self.assertContains(response, "Preview complete")
        self.assertFalse(Assignment.objects.exists())

    def test_feedback_replay_keeps_the_original_preview_settings(self):
        from .models import LessonFeedback
        self.child.lesson_theme = "space"
        self.child.save()
        url = self.library + "my-letters-v1/preview/2/?v=7&letters=QXZR&purpose=review"
        original = self.client.get(url).context
        self.client.post(url, {"action": "feedback", "kind": "change"})
        note = LessonFeedback.objects.get()
        replay = f"/feedback/{note.pk}/round/"
        self.child.delete()
        page = self.client.get(replay)
        self.assertEqual(page.context["step"], 2)
        self.assertEqual(page.context["item"], original["item"])
        self.assertEqual(page.context["lesson"]["world_key"], "space")
        self.assertEqual(page.context["purpose"], "review")
        self.assertContains(page, "Skill review")
        self.assertNotContains(page, "Add to")
        self.assertRedirects(self.client.post(replay, correct_submission(original["item"])), replay+"?step=3")
        self.assertContains(self.client.get(replay+"?step=4"), "Preview complete")
        self.assertFalse(Assignment.objects.exists())
        self.assertEqual(self.client.get(replay+"?step=-1").status_code, 404)
        self.client.force_login(get_user_model().objects.create_user("other-family"))
        self.assertEqual(self.client.get(replay).status_code, 404)
        self.assertEqual(self.client.post(replay, {"action": "skip"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(replay).status_code, 302)

    def test_whole_lesson_feedback_replays_from_the_start(self):
        from .models import LessonFeedback
        end = self.library+"keys-v1/preview/3/?v=7"
        self.client.post(end, {"action": "feedback", "kind": "worked"})
        note = LessonFeedback.objects.get()
        self.assertIsNone(note.step)
        page = self.client.get(f"/feedback/{note.pk}/round/")
        self.assertEqual(page.context["step"], 0)
        self.assertEqual(page.context["variation"], 7)
        self.assertContains(page, "Whole lesson")

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

    def test_resolution_filters_reopen_permissions_and_stale_forms(self):
        from django.core import mail
        from .models import FeedbackEmailPreference
        FeedbackEmailPreference.objects.create(parent=self.parent, enabled=True)
        resolve = {"feedback": self.note.pk, "action": "resolve", "version": "0"}
        reopen_url = f"/feedback/{self.note.pk}/reopen/"
        self.client.force_login(self.staff)
        self.client.post("/dashboard/", self.reply)
        self.assertContains(self.client.get("/dashboard/"), self.reply["reply"])
        for _ in range(2):
            self.client.post("/dashboard/", resolve)
        self.assertNotContains(self.client.get("/dashboard/"), self.reply["reply"])
        self.assertContains(self.client.get("/dashboard/?resolution=resolved&state=read"), self.reply["reply"])
        self.assertEqual(len(mail.outbox), 2)
        outsider = get_user_model().objects.create_user("another-parent")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(reopen_url, {"version": 1}).status_code, 404)
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reopen_url).status_code, 405)
        self.assertEqual(self.client.post(reopen_url, {"version": 1, "reason": "x" * 1501}).status_code, 400)
        for _ in range(2):
            self.client.post(reopen_url, {"version": 1, "reason": "Still hard to hear."})
        self.assertEqual(self.client.post("/dashboard/", resolve).status_code, 403)
        self.client.force_login(self.staff)
        self.client.post("/dashboard/", resolve)
        self.client.post("/dashboard/", self.reply)  # A replayed old reply cannot acknowledge a new follow-up.
        self.note.refresh_from_db()
        self.assertFalse(self.note.resolved)
        self.assertIsNone(self.note.read_at)
        self.assertEqual(self.note.status_version, 2)
        self.assertEqual(list(self.note.replies.values_list("kind", flat=True)), ["reply", "resolve", "reopen"])
        for link in ("/dashboard/?state=unread&lesson=keys-v1&resolution=open", "/dashboard/?resolution=all"):
            self.assertContains(self.client.get(link), "Still hard to hear.")
        self.client.post("/dashboard/", dict(resolve, version=2))
        self.client.force_login(self.parent)
        self.client.post(reopen_url, {"version": 1})
        self.note.refresh_from_db()
        self.assertTrue(self.note.resolved)
        self.client.post(reopen_url, {"version": 3})
        self.note.refresh_from_db()
        self.assertFalse(self.note.resolved)
        self.assertEqual(len(mail.outbox), 3)

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
        from .practice import build_round, original_round_count, round_count
        original = deepcopy(LESSONS)
        for key, base in LESSONS.items():
            examples = []
            sample = [*range(min(round_count(key), 24)), original_round_count(key), round_count(key)-1]
            for n in sample:
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

    def test_full_target_sets_are_playable(self):
        from string import ascii_lowercase, ascii_uppercase, digits
        from .practice import build_round, original_round_count, round_count
        from .themes import themed_round

        expected = {"keys-v2": ascii_uppercase, "letters-v1": ascii_uppercase, "shift-v1": ascii_uppercase,
                    "alphabet-gap-v1": ascii_uppercase, "my-letters-v1": ascii_uppercase, "key-check-v1": ascii_uppercase,
                    "case-match-v1": ascii_lowercase, "lowercase-v1": ascii_lowercase,
                    "number-keys-v2": digits, "digits-v1": digits, "digits-v2": list(map(str,range(21))), "five-v1": list(map(str, range(6))),
                    "ten-v1": list(map(str, range(11))), "hear-number-v1": list(map(str, range(13))),
                    "clock-v1": [f"{h}:{m:02d}" for h in range(1,13) for m in (0,30)]}
        for key, targets in expected.items():
            found = set()
            first = original_round_count(key)
            for n in range(first, min(round_count(key), first+320)):
                rows = themed_round(key, build_round(key, n), "space", n)["items"]
                found.update(item["answer"] for item in (rows[:1] if key == "key-check-v1" else rows))
            self.assertEqual(found, set(targets), key)
        for key, op in (("add-groups-v1", "+"), ("take-away-v1", "−")):
            equations = set()
            for n in range(32, 320):
                items = build_round(key, n)["items"]
                current = {item["equation"] for item in items}
                self.assertEqual(len(current), 5)
                equations.update(current)
            self.assertEqual(equations, {f"{a} {op} {b}" for a in range(11)
                                         for b in range(1 + (a if op == "−" else 10-a))})

    def test_allocator_uses_whole_pool_then_recycles_older_rounds(self):
        from .views import question_set, suggested_round
        from .practice import round_count
        child = Learner.objects.create(parent=get_user_model().objects.create_user("shuffle-parent"), nickname="Fern")
        key = "story-v1"
        history = []
        for _ in range(round_count(key)):
            n = suggested_round(child, key, history)
            self.assertNotIn(n, history)
            if history:
                self.assertNotEqual(question_set(child, key, n), question_set(child, key, history[-1]))
            history.append(n)
        self.assertIn(suggested_round(child, key, history), history[:len(history)//2])

    def test_key_and_counting_rounds_sample_without_replacement(self):
        from .practice import CURRENT_VERSION, build_round
        for original, current in CURRENT_VERSION.items():
            for number in (0, 1, 17, 999, 9999):
                lesson = build_round(current, number)
                items = lesson["items"]
                if current == "digits-v2":
                    self.assertEqual(len(items), 5)
                    self.assertEqual(len({item["answer"] for item in items}), 5)
                    self.assertTrue(all(0 <= int(item["answer"]) <= 20 for item in items))
                    continue
                self.assertEqual(items[:3], build_round(original, number)["items"])
                self.assertEqual(len(items), 5 if lesson["kind"] == "key" else 3)
                self.assertEqual(len({item["answer"] for item in items}), len(items))

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
        self.assertEqual(child.assignment_set.count(), 1)
        self.client.post(f"/children/{child.pk}/",{"action":"play"})
        play_url = f"/play/{row.pk}/"
        self.client.post(play_url, {"step":0,"answer":seen["items"][0]["answer"]})
        for _ in range(2):
            self.assertEqual(self.client.get(play_url).context["item"], seen["items"][1])
        for step, item in enumerate(seen["items"][1:], 1):
            self.client.post(play_url, {"step": step, "answer": item["answer"]})
        self.client.force_login(parent)
        self.client.post(library, {"lesson": key})
        repeat = child.assignment_set.last()
        self.assertNotEqual(repeat.variation, 17)
        self.assertNotEqual(repeat.round_snapshot["items"], seen["items"])
        self.assertEqual(repeat.round_snapshot, build_round(key, repeat.variation))


class DrawingTests(TestCase):
    def test_art_measures_and_blank_or_forged_input(self):
        from .art import art_item, evaluate
        mask = art_item({"shape":"leaf"})["mask"]
        self.assertIn("Shape filled: 100%. Color outside the outline: 0%",evaluate("color",mask,mask))
        self.assertIn("Shape filled: 0%. Color outside the outline: 100%",evaluate("color",mask,"1"+"0"*767))
        self.assertIsNone(evaluate("color",mask,"0"*768))
        self.assertIsNone(evaluate("color",mask,"9"*768))
        mask = art_item({"shape":"butterfly"})["mask"]
        reflected = "".join(mask[i-i%32+31-i%32] if i%32>=16 else "0" for i in range(768))
        self.assertIn("100%",evaluate("mirror",mask,reflected))
        self.assertIsNone(evaluate("mirror",mask,"1"*768))
        self.assertNotIn("%",evaluate("draw",mask,reflected))

    def test_finished_artwork_is_visible_to_parent(self):
        from .art import art_item
        parent = get_user_model().objects.create_user("artist-parent")
        child = Learner.objects.create(parent=parent, nickname="Artist")
        row = child.assignment_set.create(lesson="color-v1")
        self.client.force_login(parent)
        self.client.post(f"/children/{child.pk}/",{"action":"play"})
        url = f"/play/{row.pk}/"
        self.assertContains(self.client.get(url),'id="board"')
        mask = art_item({"shape":"leaf"})["mask"]
        self.client.post(url,{"step":0,"pixels":mask})
        row.refresh_from_db()
        self.assertEqual(row.artwork["pixels"],mask)
        self.client.force_login(parent)
        self.assertContains(self.client.get("/"),"View finished picture")


class ProgressionTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("placement-parent")
        self.child = Learner.objects.create(parent=self.parent, nickname="Bee")

    def open_child(self):
        self.client.force_login(self.parent)
        self.client.post(f"/children/{self.child.pk}/", {"action": "play"})

    def test_first_try_retry_and_duplicate_are_one_observation(self):
        from .models import SkillSample
        row = self.child.assignment_set.create(lesson="keys-v1")
        self.open_child()
        url = f"/play/{row.pk}/"
        for answer in ["X","X","S","S"]:
            self.client.post(url, {"step":0,"answer":answer})
        sample = SkillSample.objects.get()
        self.assertEqual((sample.score,sample.strand,sample.level),(0,"Keyboard use",1))
        self.client.post(url, {"step":1,"answer":"A"})
        self.assertEqual(SkillSample.objects.filter(score=100).count(),1)

    def test_checkin_advances_on_miss_and_parent_sees_results(self):
        from .progression import Progress
        row = self.child.assignment_set.create(lesson="number-check-v1")
        self.open_child()
        for i,answer in enumerate(["2","3","24"]):
            self.client.post(f"/play/{row.pk}/", {"step":i,"answer":answer})
        self.assertEqual(list(row.samples.order_by("step").values_list("level","score")),[(1,0),(3,100),(5,100)])
        p = Progress(self.child)
        self.assertGreater(p.estimates["Number sense"],2)
        self.client.force_login(self.parent)
        self.assertContains(self.client.get("/"),"67% across 3 scored steps")

    def test_tier_gain_only_on_a_new_personal_best_in_the_same_skill(self):
        row = self.child.assignment_set.create(lesson="number-check-v1")
        self.open_child()
        def answer(step):
            return self.client.post(f"/play/{row.pk}/", {"step": step, "answer": "3"}, HTTP_ACCEPT="application/json")
        self.assertNotIn("tier_gain", answer(0).json())  # First placement.
        self.assertEqual(answer(1).json()["tier_gain"], {"strand": "Number sense", "tier": 3})
        self.assertEqual(answer(1).status_code, 302)  # A repeat cannot award it again.
        self.assertEqual(list(row.samples.order_by("step").values_list("peak_tier", flat=True)), [2, 3])
        from .progression import record_tier
        # Historical scores predate milestone tracking. Recover their high before awarding.
        row.samples.update(peak_tier=None)
        for step in range(2, 30):
            row.samples.create(step=step, strand="Number sense", level=1, score=0)
        sample = row.samples.create(step=30, strand="Number sense", level=1, score=100)
        self.assertIsNone(record_tier(sample, self.child.pk))
        self.assertEqual(sample.peak_tier, 3)

    def test_empty_queue_guard_and_sibling_isolation(self):
        from .progression import Progress
        self.open_child()
        picks = Progress(self.child).recommendations()
        self.assertEqual(len(picks),3)
        self.assertContains(self.client.get("/"),picks[0]["title"])
        self.client.post("/suggestions/start/",{"lesson":picks[0]["key"]})
        self.client.post("/suggestions/start/",{"lesson":picks[1]["key"]})
        self.assertEqual(self.child.assignment_set.count(),1)
        sibling = Learner.objects.create(parent=self.parent,nickname="Sapling")
        self.assertEqual(sibling.assignment_set.count(),0)

    def test_tiers_trends_and_fluent_round_rest(self):
        from .models import SkillSample
        from .progression import Progress, band
        from django.utils import timezone
        self.assertEqual([band(level,3) for level in range(1,6)],[
            "Below level","Slightly below level","On level","Slightly above level","Above level"])
        self.assertTrue(all(1<=lesson["level"]<=5 and lesson["strand"] for lesson in LESSONS.values()))
        for scores in [[0,100,0],[100]*3,[100]*3]:
            row = self.child.assignment_set.create(lesson="count1-v1",step=3,completed=timezone.now())
            for step,score in enumerate(scores):
                SkillSample.objects.create(assignment=row,step=step,strand="Number sense",level=1,score=score)
        progress = Progress(self.child)
        self.assertEqual(progress.timeline()[1]["change"],67)
        chart, = progress.charts()
        self.assertEqual(len(chart["points"]), 3)
        self.assertGreater(chart["points"][-1]["level"], chart["points"][0]["level"])
        self.open_child()
        self.assertContains(self.client.get("/"), "My progress")
        self.assertContains(self.client.get("/"), "9 scored steps across 3 rounds")
        self.assertNotIn("count1-v2",[s["key"] for s in progress.recommendations()])
        self.assertEqual(progress.label(LESSONS["keys-v1"]),"Placement pending")

    def test_weak_strand_is_prioritized_and_checkins_come_due(self):
        from datetime import timedelta
        from django.utils import timezone
        from .progression import Progress
        from .models import SkillSample
        for key, score in [("count1-v1", 0), ("keys-v1", 100)]:
            row = self.child.assignment_set.create(lesson=key, step=3, completed=timezone.now())
            for step in range(3):
                SkillSample.objects.create(assignment=row, step=step, strand=LESSONS[key]["strand"], level=1, score=score)
        progress = Progress(self.child)
        picks = progress.recommendations()
        self.assertEqual(LESSONS[picks[0]["key"]]["strand"], "Number sense")
        self.assertEqual(len({p["key"] for p in picks}), len(picks))
        when = timezone.now()-timedelta(days=29)
        row = self.child.assignment_set.create(lesson="number-check-v1", completed=when, step=3)
        for step in range(3):
            SkillSample.objects.create(assignment=row, step=step, strand="Number sense", level=1, score=100)
        checks = Progress(self.child).checkins()
        self.assertEqual(next(c["reason"] for c in checks if c["key"]=="number-check-v1"), "Recheck suggested")


class QueueAndPaceTests(TestCase):
    def setUp(self):
        self.parent = get_user_model().objects.create_user("timing-parent")
        self.client.force_login(self.parent)
        self.child = Learner.objects.create(parent=self.parent, nickname="Sprout")
        self.manage = f"/children/{self.child.pk}/"

    def test_remove_specific_duplicate_and_block_stale_play(self):
        first, duplicate = [self.child.assignment_set.create(lesson="keys-v1") for _ in range(2)]
        self.client.post(self.manage, {"action":"remove", "row":duplicate.pk})
        self.assertEqual(list(self.child.assignment_set.filter(removed_at=None)), [first])
        self.client.post(self.manage, {"action":"play"})
        self.assertRedirects(self.client.post(f"/play/{duplicate.pk}/", {"step":0,"answer":"S"}), "/")
        self.assertFalse(duplicate.samples.exists())

    def test_skip_is_idempotent_and_timing_keeps_raw_score(self):
        row = self.child.assignment_set.create(lesson="key-check-v1")
        self.client.post(self.manage, {"action":"play"})
        url = f"/play/{row.pk}/"
        for _ in range(2):
            self.client.post(url, {"step":0, "action":"skip"})
        self.client.post(url, {"step":1, "answer":"sun", "active_ms":"15000"})
        self.client.post(url, {"step":2, "action":"skip"})
        row.refresh_from_db()
        self.assertEqual((row.skipped,row.answered,row.retries), (2,1,0))
        sample = row.samples.get()
        self.assertEqual((sample.score,sample.ms_per_key), (100,5000))
        self.client.force_login(self.parent)
        self.assertContains(self.client.get("/"), "2 skipped")
        self.assertContains(self.client.get("/"), "5.0 s/key")

    def test_fluency_only_with_repeated_timed_evidence(self):
        from .progression import fit
        def samples(pace, count):
            return [dict(level=2,score=100,ms_per_key=pace)]*count
        self.assertEqual(fit(samples(5000,2)),fit(samples(60000,2)))
        self.assertGreater(fit(samples(5000,6)),fit(samples(60000,6)))
        self.assertEqual(fit(samples(None,6)),fit(samples(5000,6)))


@override_settings(CACHES={key: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                "LOCATION": f"coview-tests-{key}"} for key in ("default", "coview")})
class CoViewTests(TestCase):
    def setUp(self):
        from django.core.cache import caches
        from django.test import Client
        caches["coview"].clear()
        user = get_user_model().objects.create_user("watching-parent")
        self.client.force_login(user)
        self.child = Learner.objects.create(parent=user, nickname="Fern")
        self.device = Client()
        session = self.device.session
        session["child"] = self.child.pk
        session.save()
        self.share = f"/co-view/share/{self.child.pk}/"
        self.row = self.child.assignment_set.create(lesson="signs-v1")
        self.payload = {"screen": "lesson", "assignment": self.row.pk, "step": 0, "typed": "<b>sun</b>"}

    def test_live_frame_lifetime_and_read_only_progress(self):
        from django.core.cache import caches
        self.assertFalse(self.device.post(self.share, self.payload).json()["watching"])
        self.assertIsNone(caches["coview"].get(f"frame:{self.child.pk}"))
        def watch():
            return self.client.post("/co-view/watch/", {"child": "all"}).json()["children"][str(self.child.pk)]
        self.assertIsNone(watch())
        self.assertTrue(self.device.post(self.share, self.payload).json()["watching"])
        frame = watch()
        self.assertEqual(frame["state"]["typed"], "<b>sun</b>")
        self.assertNotIn("<b>sun</b>", frame["html"])
        self.row.refresh_from_db()
        self.assertEqual(self.row.step, 0)
        self.assertFalse(self.row.samples.exists())
        self.row.step = 1
        self.row.save()
        self.assertIsNone(watch())
        self.assertEqual(self.device.post(self.share, self.payload).status_code, 404)
        self.device.post(self.share, {"screen": "garden"})
        self.assertIn("My lessons", watch()["html"])
        caches["coview"].delete(f"watch:{self.child.pk}")
        self.assertFalse(self.device.post(self.share, {"screen": "garden"}).json()["watching"])
        self.assertIsNone(watch())

    def test_household_and_child_boundaries(self):
        outsider = get_user_model().objects.create_user("other-family")
        other = Learner.objects.create(parent=outsider, nickname="Clover")
        wrong = other.assignment_set.create(lesson="keys-v1")
        self.assertEqual(self.client.post("/co-view/watch/", {"child": other.pk}).status_code, 404)
        self.assertEqual(self.device.post("/co-view/watch/", {"child": "all"}).status_code, 302)
        self.assertEqual(self.client.post(self.share, self.payload).status_code, 404)
        self.assertEqual(self.device.post(f"/co-view/share/{other.pk}/", self.payload).status_code, 404)
        frames = self.client.post("/co-view/watch/", {"child": "all"}).json()["children"]
        self.assertEqual(list(frames), [str(self.child.pk)])
        self.assertEqual(self.device.post(self.share, dict(self.payload, assignment=wrong.pk)).status_code, 404)

    def test_ladybug_catches_advance_quietly_until_the_last_catch(self):
        self.row.lesson = "ladybugs-v1"
        self.row.save()
        def watch():
            return self.client.post("/co-view/watch/", {"child": "all"}).json()["children"][str(self.child.pk)]
        watch()
        items = LESSONS[self.row.lesson]["items"]
        for step, item in enumerate(items):
            self.device.post(self.share, dict(self.payload, step=step))
            with self.captureOnCommitCallbacks(execute=True):
                reply = self.device.post(f"/play/{self.row.pk}/", {"step": step, "answer": item["answer"]},
                                         HTTP_ACCEPT="application/json")
            final = step == len(items) - 1
            self.assertEqual(reply.json()["result"], "correct" if final else "advance")
            if final:
                self.assertEqual(watch()["celebration"], "correct")
            else:
                self.assertIsNone(watch())
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.completed)
        self.assertEqual(self.row.answered, len(items))
        self.assertEqual(self.row.retries, 0)

    def test_mirror_keeps_the_answered_step_until_celebration_ends(self):
        from django.core.cache import caches
        def watch():
            return self.client.post("/co-view/watch/", {"child": "all"}).json()["children"][str(self.child.pk)]
        items = LESSONS[self.row.lesson]["items"]
        last_step = self.row.step = len(items) - 1
        answer = items[last_step]["answer"]
        self.row.save()
        watch()
        payload = dict(self.payload, step=last_step, typed=answer)
        self.device.post(self.share, payload)
        original = watch()["html"]
        with self.captureOnCommitCallbacks(execute=True):
            reply = self.device.post(f"/play/{self.row.pk}/", {"step": last_step, "answer": answer},
                                     HTTP_ACCEPT="application/json")
        self.assertEqual(reply.json()["result"], "correct")
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.completed)
        self.assertEqual(self.device.post(self.share, payload).status_code, 200)
        frame = watch()
        self.assertEqual(frame["html"], original)
        self.assertEqual(frame["celebration"], "correct")
        self.assertEqual(frame["state"]["typed"], answer)
        # Even if the next screen arrives before the viewer polls, it can play
        # the answered prompt once, complete with the submitted answer.
        self.device.post(self.share, {"screen": "garden"})
        garden = watch()
        self.assertEqual(garden["scene"], "garden")
        success = garden["success"]
        self.assertEqual(success["scene"], f"{self.row.pk}:{last_step}")
        self.assertEqual(success["html"], original)
        self.assertEqual(success["state"]["typed"], answer)
        seen = {str(self.child.pk): {"seen": success["scene"]}}
        import json
        acknowledged = self.client.post("/co-view/watch/", {"child": "all", "signals": json.dumps(seen)})
        self.assertNotIn("success", acknowledged.json()["children"][str(self.child.pk)])
        self.device.post(self.share, payload)
        caches["coview"].delete(f"celebration:{self.child.pk}:{self.row.pk}:{last_step}")
        self.assertIsNone(watch())
        self.assertEqual(self.device.post(self.share, payload).status_code, 404)

    def test_peer_match_is_scoped_to_the_live_page_and_viewer(self):
        import json
        from django.core.cache import caches
        key = str(self.child.pk)
        peer, source = "a"*32, "b"*32
        sdp = "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
        def poll(**signal):
            return self.client.post("/co-view/watch/", {"child": key, "signals": json.dumps({key: signal})}).json()
        def send(**extra):
            return self.device.post(self.share, dict(self.payload, source=source, **extra)).json()
        poll()
        send()
        poll(id=peer, source="c"*32, offer=sdp)
        self.assertIsNone(send()["offer"])
        poll(id=peer, source=source, offer=sdp)
        self.assertEqual(send()["offer"], {"id": peer, "sdp": sdp})
        send(peers=peer, answer=json.dumps({"id": peer, "sdp": sdp}))
        self.assertEqual(poll(id=peer, source=source, offer=sdp)["signals"][key]["answer"], sdp)
        self.assertEqual(poll(id="d"*32, source=source)["signals"][key], {})
        caches["coview"].delete(f"relay:{key}")
        self.assertTrue(poll(id=peer, source=source, direct=True, scene=f"{self.row.pk}:0")["children"][key]["reuse"])
        self.assertFalse(send(metadata="1")["relay"])
        self.assertIsNone(caches["coview"].get(f"frame:{key}")["state"])
        poll()  # Another parent tab needs relayed data.
        self.assertTrue(send()["relay"])

class LessonThemeTests(TestCase):
    def test_every_theme_preserves_round_structure_and_playable_targets(self):
        from copy import deepcopy
        from pathlib import Path
        from django.conf import settings
        from .art import art_item
        from .practice import CURRENT_LESSONS, build_round
        from .themes import THEMES, themed_round
        for key in CURRENT_LESSONS:
            for variation in (0, 1, 2):
                base = build_round(key, variation)
                original = deepcopy(base)
                for theme in THEMES:
                    with self.subTest(key=key, variation=variation, theme=theme):
                        lesson = themed_round(key, base, theme, variation)
                        for field in ("kind", "strand", "level", "participation"):
                            self.assertEqual(lesson[field], base[field])
                        self.assertEqual(len(lesson["items"]), len(base["items"]))
                        for before, item in zip(base["items"], lesson["items"]):
                            if item["choices"]:
                                self.assertIn(item["answer"], item["choices"])
                            if item["answer"].isdigit() and key != "key-check-v1":
                                self.assertEqual(before["answer"], item["answer"])
                            if "word" in item:
                                self.assertTrue((Path(settings.BASE_DIR)/"static"/"phonics"/"words"/(item["word"] + ".ogg")).is_file())
                            if "pictures" in item:
                                self.assertIn(item["answer"], [pic["label"] for pic in item["pictures"]])
                            if "shape" in item:
                                self.assertIn("1", art_item(item)["mask"])
                            if "tiles" in item:
                                self.assertCountEqual(item["answer"].split(), item["tiles"])
                        if theme != "garden":
                            self.assertEqual(lesson["world"]["label"], THEMES[theme]["label"])
                self.assertEqual(base, original)

    def test_theme_is_per_child_and_opened_round_keeps_its_answers(self):
        from django.test import Client
        from .views import assign_lesson
        parent = get_user_model().objects.create_user("theme-parent")
        self.client.force_login(parent)
        child = Learner.objects.create(parent=parent, nickname="Pip")
        sibling = Learner.objects.create(parent=parent, nickname="Fern")
        row = assign_lesson(child, "signs-v1", 0)
        manage = f"/children/{child.pk}/"
        self.client.post(manage, {"action":"theme","theme":"space"})
        self.assertEqual(self.client.post(manage, {"action":"theme","theme":"unknown"}).status_code, 400)
        device = Client()
        device.force_login(parent)
        device.post(manage, {"action":"play"})
        url = f"/play/{row.pk}/"
        preview = self.client.get(manage + "library/signs-v1/preview/0/").context["item"]
        played = device.get(url).context["item"]
        self.assertEqual(played, preview)
        self.client.post(manage, {"action":"theme","theme":"bakery"})
        self.assertEqual(device.get(url).context["item"], played)
        device.post(url, {"step":0, "answer":played["answer"]})
        row.refresh_from_db()
        self.assertEqual((row.step, row.samples.count()), (1,1))
        child.refresh_from_db()
        next_row = assign_lesson(child, "signs-v1", 0)
        self.assertEqual(device.get(f"/play/{next_row.pk}/").context["lesson"]["world_key"], "bakery")
        sibling.refresh_from_db()
        self.assertEqual(sibling.lesson_theme, "garden")
        outsider = get_user_model().objects.create_user("another-theme-parent")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(manage, {"action":"theme","theme":"farm"}).status_code, 404)

    def test_all_mazes_reach_the_leaf(self):
        from .practice import GARDEN_PRACTICE
        for item in LESSONS["arrow-maze-v1"]["items"] + GARDEN_PRACTICE["arrow-maze-v1"]:
            maze = item["maze"]
            reachable = [maze.index("B")]
            for cell in reachable:
                for neighbor in (cell-1, cell+1, cell-5, cell+5):
                    if (0 <= neighbor < len(maze) and abs(neighbor%5-cell%5) <= 1
                        and maze[neighbor] != "#" and neighbor not in reachable):
                        reachable.append(neighbor)
            self.assertIn(maze.index("L"), reachable)
