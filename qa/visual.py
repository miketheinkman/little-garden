"""Run with manage.py test qa.visual. Django creates a disposable test database."""
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from pilot.models import Learner, SkillSample


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
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for device, width in [("desktop", 1200), ("phone", 375)]:
                for theme in ("light", "dark"):
                    with self.subTest(device=device, theme=theme):
                        self.variant = f"{device}-{theme}"
                        with browser.new_context(viewport={"width": width, "height": 820}, color_scheme="light") as ctx:
                            self.exercise(ctx.new_page(), theme)
            browser.close()

    def exercise(self, page, theme):
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
        page.get_by_role("button", name="Open Fern’s garden").click()
        expect(page.get_by_role("heading", name="My progress")).to_be_visible()
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        self.capture(page, "child")
        picker.select_option("system")
        for scheme in ("dark", "light"):
            page.emulate_media(color_scheme=scheme)
            expect(page.locator("html")).to_have_attribute("data-theme", scheme)
        self.assertEqual(errors, [])
