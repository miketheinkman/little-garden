"""Run with manage.py test qa.visual. Django creates a disposable test database."""
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from pilot.models import Learner, SkillSample
from pilot.views import assign_lesson


@override_settings(CACHES={key: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                "LOCATION": f"visual-review-{key}"} for key in ("default", "coview")})
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

    def test_family_co_view(self):
        from django.core.cache import caches
        fern = Learner.objects.get(pk=self.child_id)
        ash = Learner.objects.create(parent=fern.parent, nickname="Ash")
        art = assign_lesson(fern, "color-v1")
        typing_rows = iter([assign_lesson(ash, "signs-v1", variation=0) for _ in range(4)])
        trail = assign_lesson(fern, "lines-v1")
        parent = Client()
        parent.force_login(fern.parent)
        cookies = [parent.cookies["sessionid"].value]
        for child in (fern, ash):
            device = Client()
            device.force_login(child.parent)
            device.post(reverse("manage", args=[child.pk]), {"action": "play"})
            cookies.append(device.cookies["sessionid"].value)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for size, width in (("desktop", 1200), ("phone", 375)):
                for theme in ("light", "dark"):
                    typing = next(typing_rows)
                    caches["coview"].clear()
                    self.variant = f"{size}-{theme}"
                    with self.subTest(size=size, theme=theme):
                        contexts = []
                        pages = []
                        for cookie in cookies:
                            context = browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme)
                            contexts.append(context)
                            context.add_cookies([{"name": "sessionid", "value": cookie, "url": self.live_server_url}])
                            pages.append(context.new_page())
                        try:
                            viewer, painter, typist = pages
                            viewer.goto(self.live_server_url)
                            viewer.get_by_role("link", name="Watch live").click()
                            picker = viewer.get_by_label("Show", exact=True)
                            picker.select_option("all")
                            fern_tile = viewer.locator(f'[data-child="{fern.pk}"]')
                            ash_tile = viewer.locator(f'[data-child="{ash.pk}"]')
                            expect(fern_tile).to_contain_text("Waiting for an open garden")
                            self.capture(viewer, "coview-waiting")
                            painter.goto(self.live_server_url + reverse("play", args=[art.pk]))
                            typist.goto(self.live_server_url + reverse("play", args=[typing.pk]))
                            expect(painter.locator("#live-presence")).to_contain_text("watching along")
                            painter.locator("#board").press("Space")
                            typist.locator('input[name="answer"]').fill("sun")
                            expect(ash_tile.locator("output")).to_have_text("sun")
                            board = fern_tile.locator("canvas")
                            expect(board).to_be_visible()
                            viewer.wait_for_function(
                                """() => document.querySelector('.live-art')?.getContext('2d')
                                             .getImageData(321,241,1,1).data[0] === 212""")
                            self.capture(viewer, "coview-together")
                            picker.select_option(str(ash.pk))
                            expect(fern_tile).to_be_hidden()
                            typist.locator('input[name="answer"]').fill("fern bed")
                            expect(ash_tile.locator("output")).to_have_text("fern bed")
                            self.capture(viewer, "coview-single")
                            typist.locator('input[name="answer"]').fill("red pot")
                            typist.get_by_role("button", name="Check sign").click()
                            expect(ash_tile).to_contain_text("Answered red pot")
                            expect(ash_tile).to_contain_text("Step 2 of 3")
                            picker.select_option(str(fern.pk))
                            painter.goto(self.live_server_url + reverse("play", args=[trail.pk]))
                            expect(fern_tile.locator(".live-trail")).to_be_visible()
                            points = painter.locator("#guide").evaluate("""path => [0, 8, 16, 24, 32].map(n => {
                                const p = path.getPointAtLength(n).matrixTransform(path.getScreenCTM());
                                return [p.x, p.y];
                            })""")
                            painter.mouse.move(*points[0])
                            painter.mouse.down()
                            for point in points[1:]:
                                painter.mouse.move(*point)
                            painter.mouse.up()
                            viewer.wait_for_function("""() => {
                                const ink = document.querySelector('.live-ink');
                                return ink && parseFloat(ink.style.strokeDashoffset) < ink.getTotalLength() - 5;
                            }""")
                            painter.goto(self.live_server_url)
                            expect(fern_tile).to_contain_text("My lessons")
                            if size == "phone" and theme == "dark":
                                painter.close()
                                expect(fern_tile).to_contain_text("Waiting for an open garden", timeout=12500)
                                expect(fern_tile.get_by_role("heading", name="My lessons")).to_have_count(0)
                        finally:
                            for context in contexts:
                                context.close()
            browser.close()

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
