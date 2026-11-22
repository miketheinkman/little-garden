"""Run with manage.py test qa.visual. Django creates a disposable test database."""
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from pilot.models import Learner, SkillSample
from pilot.views import assign_lesson


class VisualReview(StaticLiveServerTestCase):
    def setUp(self):
        password = "garden-qa-only"
        get_user_model().objects.create_user("reviewer", password=password, is_staff=True)
        learner = Learner.objects.create(parent=get_user_model().objects.get(username="reviewer"), nickname="Fern")
        for scores in [(0, 100, 0), (100, 100, 100)]:
            assignment = learner.assignment_set.create(lesson="keys-v1", completed=timezone.now(), step=3)
            for index, score in enumerate(scores):
                SkillSample.objects.create(assignment=assignment, step=index, strand="Keyboard use", level=1, score=score)
        self.child_id = learner.pk
        self.out = Path("visual-results")
        self.out.mkdir(exist_ok=True)

    def capture(self, page, name):
        page.screenshot(path=self.out / f"{self.variant}-{name}.png", full_page=True, animations="disabled")
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"), name)

    def test_feature_screens(self):
        for device, width in [("desktop", 1200), ("phone", 375)]:
            for theme in ("light", "dark"):
                with self.subTest(device=device, theme=theme):
                    self.variant = f"{device}-{theme}"
                    learner = Learner.objects.get(pk=self.child_id)
                    kept = assign_lesson(learner, "keys-v2", variation=0)
                    duplicate = assign_lesson(learner, "keys-v2", variation=0)
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
                        with browser.new_context(viewport={"width": width, "height": 820}, color_scheme="light") as ctx:
                            self.exercise(ctx.new_page(), theme, kept.pk)
                        browser.close()
                    duplicate.refresh_from_db()
                    self.assertIsNotNone(duplicate.removed_at)
                    kept.refresh_from_db()
                    self.assertEqual(kept.skipped, 2)
                    self.assertGreater(kept.samples.get(step=0).ms_per_key, 0)

    def exercise(self, page, theme, kept_id):
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.live_server_url)
        picker = page.get_by_label("Theme", exact=True)
        picker.select_option(theme)
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        page.get_by_role("button", name="Replay opening").click()
        self.assertGreater(page.locator(".meadow-scene").evaluate(
            "(scene) => scene.getAnimations({subtree:true}).length"), 0)
        self.capture(page, "welcome")
        page.emulate_media(reduced_motion="reduce")
        expect(page.get_by_role("button", name="Replay opening")).to_be_hidden()
        self.assertEqual(page.locator(".meadow-scene").evaluate(
            "(scene) => scene.getAnimations({subtree:true}).length"), 0)
        page.get_by_role("link", name="Enter the garden").click()
        expect(page).to_have_url(self.live_server_url + "/login/")
        page.emulate_media(reduced_motion="no-preference")
        self.capture(page, "login")
        page.locator("#id_username").fill("reviewer")
        page.locator("#id_password").fill("garden-qa-only")
        page.locator("#id_password").press("Enter")
        page.wait_for_url(self.live_server_url + "/")
        self.capture(page, "parent")

        page.get_by_role("link", name="Browse lesson library").click()
        self.capture(page, "library")
        card = page.locator("article").filter(has=page.get_by_role("heading", name="Count the seeds", exact=True))
        expect(card).to_contain_text("5 steps")
        card.get_by_role("link", name="Preview lesson").click()
        page.get_by_role("navigation", name="Preview steps").get_by_role("link", name="5").click()
        expect(page.get_by_text("Step 5 of 5", exact=True)).to_be_visible()
        self.capture(page, "five-count-preview")
        page.goto(self.live_server_url + reverse("preview", args=[self.child_id,"color-v1",0]))
        board = page.locator("#board")
        board.focus()
        board.press("Space")
        expect(page.get_by_role("button", name="Finish picture")).to_be_enabled()
        self.capture(page, "drawing")
        page.get_by_role("button", name="What worked").click()
        expect(page.locator("#feedback-status")).to_contain_text("Saved")
        page.get_by_role("link", name="Review saved feedback").click()
        self.capture(page, "feedback")
        page.get_by_role("link", name="Admin dashboard").click()
        self.capture(page, "admin")

        page.goto(self.live_server_url)
        self.capture(page, "queue-controls")
        page.get_by_role("button", name="Remove", exact=True).last.click()
        expect(page.get_by_role("button", name="Remove", exact=True)).to_have_count(1)
        page.get_by_role("button", name="Open Fern’s garden").click()
        expect(page.get_by_role("heading", name="My progress")).to_be_visible()
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        self.capture(page, "child")
        page.get_by_role("link", name="Start lesson").click()
        expect(page).to_have_url(self.live_server_url + reverse("play", args=[kept_id]))
        self.capture(page, "skip-question")
        page.locator("body").click(position={"x": 1, "y": 1})
        page.keyboard.press("s")
        expect(page.get_by_text("Step 2 of 5", exact=True)).to_be_visible()
        page.get_by_role("button", name="Skip this question").click()
        page.get_by_role("button", name="Skip this question").click()
        expect(page.get_by_text("Step 4 of 5", exact=True)).to_be_visible()
        page.keyboard.press("s")
        expect(page.get_by_text("Step 5 of 5", exact=True)).to_be_visible()
        self.capture(page, "five-key-finish")
        page.keyboard.press("m")
        expect(page).to_have_url(self.live_server_url + "/")
        page.get_by_role("link", name="Parent sign in").click()
        page.locator("#id_username").fill("reviewer")
        page.locator("#id_password").fill("garden-qa-only")
        page.locator("#id_password").press("Enter")
        page.get_by_text("Skill placement and progress", exact=True).click()
        expect(page.get_by_text("s/key (median)", exact=False).first).to_be_visible()
        page.get_by_text("This week’s learning record", exact=True).click()
        expect(page.get_by_text("2 skipped", exact=False).first).to_be_visible()
        self.capture(page, "keyboard-progress")
        picker.select_option("system")
        for scheme in ("dark", "light"):
            page.emulate_media(color_scheme=scheme)
            expect(page.locator("html")).to_have_attribute("data-theme", scheme)
        self.assertEqual(errors, [])
