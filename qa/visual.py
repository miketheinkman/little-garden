"""Run with manage.py test qa.visual. Django creates a disposable test database."""
import os
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from pilot.invitations import code_digest
from pilot.models import Learner, ParentInvitation, SkillSample
from pilot.practice import LESSONS
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

    @override_settings(INVITE_ONLY_SIGNUP=True)
    def test_parent_invitation(self):
        from datetime import timedelta
        cases = [(width, theme, f"invitation-{width}-{theme}")
                 for width in (375, 1200) for theme in ("light", "dark")]
        for _, _, code in cases:
            ParentInvitation.objects.create(email=f"{code}@example.org", code_digest=code_digest(code),
                                            expires_at=timezone.now() + timedelta(days=1))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, code in cases:
                self.variant = code
                email = f"{code}@example.org"
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("signup"))
                    self.capture(page, "gate")
                    page.get_by_label("Invitation code").fill("incorrect")
                    page.get_by_role("button", name="Continue").click()
                    expect(page.get_by_text("That code is invalid", exact=False)).to_be_visible()
                    self.capture(page, "error")
                    page.get_by_label("Invitation code").fill(self.variant)
                    page.get_by_role("button", name="Continue").click()
                    expect(page.get_by_label("Parent recovery email")).to_have_value(email)
                    expect(page.get_by_label("Parent recovery email")).to_be_disabled()
                    page.get_by_label("Username").fill(self.variant)
                    self.capture(page, "parent-form")
                    page.locator("#id_password1").fill("Clover-test-Garden-41")
                    page.locator("#id_password2").fill("Clover-test-Garden-41")
                    page.get_by_role("button", name="Create a parent account").click()
                    expect(page).to_have_url(self.live_server_url + "/")
            browser.close()

    @override_settings(STRIPE_TEST_ONE_TIME_LINK="https://donate.stripe.com/test_Once",
                       STRIPE_TEST_MONTHLY_LINK="https://buy.stripe.com/test_Monthly")
    def test_donation_links(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    self.variant = f"donations-{width}-{theme}"
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        page = ctx.new_page()
                        # Isolate the app-to-Stripe handoff from the third-party checkout.
                        page.route(re.compile(r"^https://(?:buy|donate)\.stripe\.com/test_"), lambda route: route.fulfill(
                            status=200, content_type="text/plain", body="Test checkout destination"))
                        page.goto(self.live_server_url + reverse("mission"))
                        for label, url in (("Give once", "https://donate.stripe.com/test_Once"),
                                           ("Give monthly", "https://buy.stripe.com/test_Monthly")):
                            link = page.get_by_role("link", name=label, exact=True)
                            link.focus()
                            if label == "Give once":
                                self.capture(page, "mission")
                            link.press("Enter")
                            expect(page).to_have_url(url)
                            page.go_back()
                        with override_settings(STRIPE_TEST_MONTHLY_LINK="", STRIPE_TEST_ONE_TIME_LINK=""):
                            page.reload()
                            expect(page.get_by_text("Online donations are coming soon.")).to_be_visible()
                            self.capture(page, "unavailable")
            browser.close()

    def test_placement_and_review_coverage(self):
        from datetime import timedelta
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        cases = [(width, theme, Learner.objects.create(parent=parent, nickname="Clover"))
                 for width in (375,1200) for theme in ("light","dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width,theme,child in cases:
                self.variant = f"reviews-{width}-{theme}"
                with browser.new_context(viewport={"width":width,"height":820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                    page = ctx.new_page()
                    page.goto(self.live_server_url)
                    page.locator(f'[data-learner="{child.pk}"] .learner-menu summary').click()
                    page.locator(f'[data-learner="{child.pk}"]').get_by_role("link",name="Placement & reviews",exact=True).click()
                    page.get_by_label("Skill area").select_option("Money sense")
                    page.get_by_role("button",name="Show",exact=True).click()
                    self.capture(page,"initial")
                    card = page.locator('[data-lesson="money-id-v1"]')
                    review_url = page.url
                    card.get_by_role("link",name="Preview check").click()
                    expect(page.locator(".preview-tools")).to_contain_text("Initial placement")
                    expect(page.get_by_role("link",name="Schedule this round")).to_have_attribute("href", re.compile("purpose=placement"))
                    page.goto(review_url)
                    card.get_by_role("button",name="Queue placement").click()
                    expect(card).to_contain_text("In queue · Initial placement")
                    card.get_by_role("link",name="Schedule review").click()
                    expect(page.get_by_label("Session purpose")).to_have_value("review")
                    expect(page.get_by_label("Repeat",exact=True)).to_have_value("fourweeks")
                    first = timezone.localdate()+timedelta(days=28)
                    expect(page.get_by_label("First available")).to_have_value(first.isoformat())
                    page.get_by_role("button",name="Schedule lesson").click()
                    expect(card).to_contain_text("Skill review scheduled")
                    url = self.live_server_url + reverse("placement_reviews",args=[child.pk])
                    page.goto(url+"?strand=Money+sense")
                    expect(card).to_contain_text("Skill review scheduled")
                    self.capture(page,"scheduled")
                    page.get_by_label("Skill area").select_option("Auditory memory")
                    page.get_by_role("button",name="Show",exact=True).click()
                    expect(page.locator(".review-lesson")).to_contain_text("Parent observation")
                    self.capture(page,"observation")
                    page.get_by_label("Coverage",exact=True).select_option("Review due")
                    page.get_by_role("button",name="Show",exact=True).click()
                    expect(page.get_by_text("No activities match these filters.")).to_be_visible()
            browser.close()

    def test_family_calendar(self):
        from datetime import timedelta
        parent = get_user_model().objects.get(username="reviewer")
        fern = Learner.objects.get(pk=self.child_id)
        ash = Learner.objects.create(parent=parent, nickname="Ash")
        today = timezone.localdate()
        day = (today.replace(day=1) + timedelta(days=32)).replace(day=9)
        fern.lessonplan_set.create(lesson="keys-v2", repeat="weekdays", next_on=day + timedelta(days=(7-day.weekday())%7))
        ash.lessonplan_set.create(lesson="ten-v1", repeat="once", next_on=day)
        family = Client()
        family.force_login(parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375,1200):
                for theme in ("light","dark"):
                    self.variant = f"calendar-{width}-{theme}"
                    with browser.new_context(viewport={"width":width,"height":850}, color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                        page = ctx.new_page()
                        page.goto(self.live_server_url)
                        page.get_by_role("link", name="Family calendar", exact=True).click()
                        expect(page.get_by_role("link",name="Today",exact=True)).to_be_visible()
                        page.get_by_role("link", name="Next month").click()
                        cell = page.locator(f'.month-grid a[href*="day={day}"]')
                        cell.focus()
                        cell.press("Enter")
                        expect(page.locator("#day-plan")).to_contain_text("Make ten")
                        self.capture(page, "month")
                        page.get_by_label("Show lessons for").select_option(str(fern.pk))
                        page.get_by_role("button",name="Show",exact=True).click()
                        expect(page.locator("#day-plan")).not_to_contain_text("Make ten")
                        page.get_by_role("link",name="Schedule for Fern").click()
                        page.get_by_label("Lesson tier").select_option(str(LESSONS["five-v1"]["level"]))
                        page.get_by_role("button", name="Filter lessons").click()
                        page.locator('[data-lesson="five-v1"] [data-schedule]').click()
                        expect(page.get_by_label("First available")).to_have_value(day.isoformat())
                        page.get_by_role("button",name="Schedule lesson").click()
                        expect(page.locator("#day-plan")).to_contain_text("Make five")
                        expect(page.get_by_label("Show lessons for")).to_have_value(str(fern.pk))
                        self.capture(page, "scheduled")
                        page.get_by_role("link",name="Previous month").click()
                        page.get_by_role("link",name="Today",exact=True).click()
                        expect(page.locator("#day-plan")).to_contain_text("No lessons scheduled for this day.")
                        self.capture(page, "empty")
                        page.get_by_role("link",name="Next month").click()
                        cell.click()
                        page.locator("#day-plan li").filter(has_text="Make five").get_by_role("link",name="Edit plan").click()
                        page.locator(".plan-row").filter(has_text="Make five").get_by_role("button",name="Cancel plan").click()
                        expect(page.locator("#day-plan")).not_to_contain_text("Make five")
            browser.close()

    def test_planner_and_tablet_questions(self):
        from datetime import timedelta

        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        child = Learner.objects.get(pk=self.child_id)
        scheduled = assign_lesson(child, "keys-v2", 0)
        route = assign_lesson(child, "water-works-v1", 0)
        device = Client()
        device.force_login(parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        tomorrow = timezone.localdate() + timedelta(days=1)
        cases = [(width, theme, Learner.objects.create(parent=parent, nickname="Fern"))
                 for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, learner in cases:
                self.variant = f"planner-{width}-{theme}"
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("planner", args=[learner.pk]))
                    expect(page.get_by_text("No upcoming plans", exact=False)).to_be_visible()
                    self.capture(page, "empty")
                    page.get_by_role("link", name="Choose a lesson to schedule").click()
                    page.get_by_label("Subject").select_option(LESSONS["ten-v1"]["category"])
                    page.get_by_role("button", name="Filter lessons").click()
                    page.wait_for_load_state("load")
                    trigger = page.locator('[data-lesson="ten-v1"] [data-schedule]')
                    trigger.focus()
                    trigger.press("Enter")
                    expect(page.get_by_role("dialog")).to_be_visible()
                    page.keyboard.press("Escape")
                    expect(trigger).to_be_focused()
                    trigger.click()
                    page.get_by_label("First available").fill(tomorrow.isoformat())
                    page.get_by_label("Repeat", exact=True).select_option("weekly")
                    page.get_by_role("button", name="Schedule lesson").click()
                    expect(page.get_by_text("Choose at least one practice day.")).to_be_visible()
                    page.screenshot(path=self.out / f"{self.variant}-choose-days.png")
                    page.get_by_label("Monday", exact=True).check()
                    expect(page.get_by_text("Choose at least one practice day.")).to_have_count(0)
                    page.get_by_label("Thursday", exact=True).check()
                    page.screenshot(path=self.out / f"{self.variant}-weekly.png")
                    self.assertFalse(page.get_by_role("dialog").evaluate("el => el.scrollWidth > el.clientWidth"))
                    page.get_by_role("button", name="Schedule lesson").click()
                    expect(page.get_by_role("dialog")).not_to_be_visible()
                    expect(trigger).to_be_visible()
                    expect(page.get_by_label("Subject")).to_have_value(LESSONS["ten-v1"]["category"])
                    page.get_by_role("link", name="Lesson planner", exact=True).click()
                    expect(page.get_by_text("Mon, Thu", exact=True)).to_be_visible()
                    self.capture(page, "saved")
                    page.get_by_role("link", name="Next week").click()
                    expect(page.locator(".plan-agenda dd")).to_have_count(2)
                    page.get_by_role("link", name="Previous week").click()
                    page.get_by_role("link", name="Edit dates").click()
                    expect(page.get_by_label("Monday", exact=True)).to_be_checked()
                    page.get_by_label("Repeat", exact=True).select_option("once")
                    page.get_by_role("button", name="Save changes").click()
                    expect(page.locator(".plan-row")).to_contain_text("Just once")
                    page.get_by_role("button", name="Cancel plan").click()
                    expect(page.get_by_text("No upcoming plans", exact=False)).to_be_visible()
            with browser.new_context(viewport={"width":1024,"height":640}, has_touch=True) as ctx:
                ctx.add_cookies([{"name":"sessionid","value":device.cookies["sessionid"].value,"url":self.live_server_url}])
                page = ctx.new_page()
                page.goto(self.live_server_url + reverse("play", args=[scheduled.pk]))
                def on_question():
                    expect(page.locator("#prompt")).to_be_focused()
                    expect(page.locator("#prompt")).to_be_in_viewport(ratio=1)
                    self.assertLess(page.locator("[data-screen-keyboard] summary").bounding_box()["y"], 640)
                on_question()
                self.variant = "landscape-tablet"
                page.screenshot(path=self.out / "landscape-tablet-question.png")
                first = scheduled.round_snapshot["items"][0]
                page.locator("[data-screen-keyboard] summary").click()
                buttons = page.locator("#activity button[name=answer]")
                buttons.filter(has_text=next(c for c in first["choices"] if c != first["answer"])).click()
                expect(page.locator(".retry-note")).to_be_visible()
                buttons.filter(has_text=first["answer"]).click()
                expect(page.get_by_text("Step 2 of 5")).to_be_visible()
                on_question()
                page.get_by_role("button",name="Skip this question").click()
                expect(page.get_by_text("Step 3 of 5")).to_be_visible()
                on_question()
                page.goto(self.live_server_url + reverse("play", args=[route.pk]))
                expect(page.locator(".route-game [data-run]")).to_be_in_viewport()
                expect(page.locator("#prompt")).to_be_in_viewport()
                page.screenshot(path=self.out / "landscape-tablet-puzzle.png")
                ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                page.goto(self.live_server_url + reverse("preview", args=[child.pk, "keys-v2", 0]))
                expect(page.locator("#prompt")).to_be_focused()
                page.locator(".preview-steps").get_by_role("link", name="2", exact=True).click()
                expect(page.locator("#prompt")).to_be_focused()
                expect(page.locator("[data-screen-keyboard] summary")).to_be_in_viewport()
            browser.close()

    def test_question_work_area(self):
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        cases = []
        for width, height in ((375, 667), (812, 375), (1024, 640), (1200, 820)):
            for theme in ("light", "dark"):
                child = Learner.objects.create(parent=parent, nickname="Fern", lesson_theme="space")
                row = assign_lesson(child, "keys-v2", 0)
                device = Client()
                device.force_login(parent)
                device.post(reverse("manage", args=[child.pk]), {"action": "play"})
                cases.append((width, height, theme, child, row, device))

        def check_position(page, start=".question-heading"):
            expect(page.locator("#prompt")).to_be_focused()
            expect(page.locator("#prompt")).to_be_in_viewport(ratio=1)
            page.wait_for_function("""selector => {
                const top = document.querySelector(selector).getBoundingClientRect().top;
                const bottom = document.querySelector('.question-work-area').getBoundingClientRect().bottom;
                const inset = Math.max(16, (innerHeight - (bottom - top)) / 2);
                return Math.abs(top - inset) < 3 ||
                    (top > inset && scrollY + innerHeight >= document.documentElement.scrollHeight - 2) ||
                    (top < inset && scrollY === 0);
            }""", arg=start)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, height, theme, child, row, device in cases:
                with browser.new_context(viewport={"width": width, "height": height}, has_touch=width < 1200,
                                         color_scheme=theme) as ctx:
                    def login(client):
                        ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": self.live_server_url}])
                    login(device)
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("play", args=[row.pk]))
                    check_position(page)
                    expect(page.locator("[data-screen-keyboard] summary")).to_be_in_viewport(ratio=1)
                    page.screenshot(path=self.out / f"work-area-{width}-{theme}-learner.png")
                    page.get_by_role("button", name="Skip this question").click()
                    expect(page.locator("[data-question-start]")).to_have_text("Step 2 of 5")
                    check_position(page)
                    login(family)
                    url = self.live_server_url + reverse("preview", args=[child.pk, "gates-switches-v1", 1]) + "?v=23"
                    page.goto(url)
                    check_position(page)
                    page.screenshot(path=self.out / f"work-area-{width}-{theme}-preview.png")
                    expect(page.locator("[data-kind=leverA]")).to_be_in_viewport(ratio=1)
                    self.assertGreaterEqual(page.locator("[data-kind=leverA]").bounding_box()["width"], 44)
                    page.get_by_role("button", name="Skip this question").click()
                    expect(page.locator(".preview-steps [aria-current]")).to_have_text("3")
                    check_position(page)
                    page.goto(url + "#feedback")
                    expect(page.locator("#feedback-note")).to_be_in_viewport()
                    expect(page.locator("#prompt")).not_to_be_focused()
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk, "scissors-v1", 0]))
                    check_position(page, "[data-parent-prep]")
                    expect(page.locator("[data-parent-prep]")).to_be_in_viewport(ratio=1)
            browser.close()

    def test_gate_throw_switch(self):
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        child = Learner.objects.get(pk=self.child_id)
        row = assign_lesson(child, "gates-switches-v1", 0)
        row.step = 3  # The double lock uses both handle markings.
        row.save(update_fields=["step"])
        device = Client()
        device.force_login(parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    options = dict(viewport={"width": width, "height": 820}, color_scheme=theme,
                                   has_touch=width == 375, reduced_motion="reduce" if theme == "dark" else "no-preference")
                    with browser.new_context(**options) as kid, browser.new_context(**options) as grownup:
                        for ctx, client in ((kid, device), (grownup, family)):
                            ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": self.live_server_url}])
                        viewer, page = grownup.new_page(), kid.new_page()
                        viewer.goto(self.live_server_url + reverse("coview"))
                        viewer.get_by_label("Show", exact=True).select_option(str(child.pk))
                        page.goto(self.live_server_url + reverse("play", args=[row.pk]))
                        board = page.locator(".route-game")
                        circle = board.get_by_role("button", name=re.compile("circle switch"))
                        triangle = board.get_by_role("button", name=re.compile("triangle switch"))
                        arm = circle.locator(".throw-arm")
                        expect(circle).to_have_attribute("aria-pressed", "false")
                        expect(circle.locator(".switch-circle")).to_be_visible()
                        expect(triangle.locator(".switch-triangle")).to_be_visible()
                        expect(circle.locator(".switch-triangle")).to_be_hidden()
                        expect(arm).to_have_css("transition-duration", "0s" if theme == "dark" else "0.26s")
                        off = arm.evaluate("el => getComputedStyle(el).transform")
                        board.locator(".route-grid").screenshot(path=self.out / f"lever-{width}-{theme}-off.png")
                        if width == 375:
                            circle.tap()
                        else:
                            circle.press("Space")
                        expect(circle).to_have_attribute("aria-pressed", "true")
                        expect(board.locator("[data-kind=gateBoth]")).to_have_attribute("aria-label", re.compile("closed"))
                        triangle.click()
                        expect(board.locator("[data-kind=gateBoth]")).to_have_attribute("aria-label", re.compile("open"))
                        mirror = viewer.locator(f'[data-child="{child.pk}"] .route-game')
                        expect(mirror.locator("[data-kind=leverA]")).to_have_attribute("data-placed", "true", timeout=10000)
                        expect(mirror.locator("[data-kind=gateBoth]")).to_have_attribute("aria-label", re.compile("open"))
                        expect(arm).not_to_have_css("transform", off)
                        board.locator(".route-grid").screenshot(path=self.out / f"lever-{width}-{theme}-on.png", animations="disabled")
                        board.locator("[data-undo]").click()
                        expect(triangle).to_have_attribute("aria-pressed", "false")
                        board.locator("[data-reset]").click()
                        expect(arm).to_have_css("transform", off)
                        expect(mirror.locator("[data-kind=leverA]")).to_have_attribute("data-placed", "false", timeout=10000)
            browser.close()

    def test_workshop_and_weekly_record(self):
        from pilot.test_puzzles import winning_moves
        from pilot.workshop import GAMES, layouts
        family = Client()
        family.force_login(get_user_model().objects.get(username="reviewer"))
        cookie = family.cookies["sessionid"].value
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375,1200):
                for theme in ("light","dark"):
                    self.variant = f"workshop-{width}-{theme}"
                    with browser.new_context(viewport={"width":width,"height":820}, color_scheme=theme, has_touch=width==375) as ctx:
                        ctx.add_cookies([{"name":"sessionid","value":cookie,"url":self.live_server_url}])
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        for key in GAMES:
                            page.goto(self.live_server_url + reverse("preview",args=[self.child_id,key,0]))
                            board = page.locator(".route-game")
                            board.locator("[data-run]").click()
                            expect(board.locator(".is-stop")).to_be_visible()
                            board.locator("[data-hint]").click()
                            expect(board.locator(".is-hint")).to_be_visible()
                            controls = board.locator(".route-editable")
                            for i, turns in enumerate(winning_moves(layouts(key,0,0))[0]):
                                for _ in range(turns):
                                    if width == 375:
                                        controls.nth(i).tap()
                                    else:
                                        controls.nth(i).press("Space")
                            board.locator("[data-run]").click()
                            expect(board.locator("[data-next]")).to_be_visible(timeout=10000)
                            board.screenshot(path=self.out / f"{self.variant}-{key}.png")
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            board.locator("[data-next]").click()
                            expect(page.get_by_text("Step 2 of 5",exact=True)).to_be_visible()
                        page.goto(self.live_server_url + reverse("weekly_record",args=[self.child_id]))
                        note = f"Recognized both shapes on the second try ({width} {theme})."
                        page.get_by_label("What did you notice?").fill(note)
                        page.get_by_role("button",name="Save observation").click()
                        expect(page.get_by_text(note,exact=True)).to_be_visible()
                        self.capture(page,"weekly-record")
                        page.emulate_media(media="print")
                        expect(page.get_by_text(note,exact=True)).to_be_hidden()
                        page.emulate_media(media="screen")
                        page.get_by_label("Include my observations").check()
                        page.emulate_media(media="print")
                        expect(page.get_by_text(note,exact=True)).to_be_visible()
                        expect(page.get_by_role("button",name="Save observation")).to_be_hidden()
                        if width == 1200 and theme == "light":
                            page.pdf(path=self.out/"weekly-record.pdf",format="Letter")
                        page.emulate_media(media="screen")
                        page.goto(self.live_server_url+reverse("preview",args=[self.child_id,"lines-v1",0]))
                        page.get_by_text("Trace with arrow steps").click()
                        right = page.get_by_role("button",name="Trace right")
                        for _ in range(10):
                            if page.locator(".answer-party").count(): break
                            right.press("ArrowRight")
                        expect(page.get_by_text(f"Step 2 of {len(LESSONS['lines-v1']['items'])}",exact=True)).to_be_visible()
                        page.goto(self.live_server_url+reverse("preview",args=[self.child_id,"signs-v1",0]))
                        page.get_by_text("Use letter buttons").click()
                        for ch in LESSONS["signs-v1"]["items"][0]["answer"]:
                            page.locator(f'[data-type="{ch}"]').click()
                        page.get_by_role("button",name="Check sign").click()
                        expect(page.get_by_text("Step 2 of 3",exact=True)).to_be_visible()
                        self.assertEqual(errors,[])
            browser.close()

    def test_answer_sounds(self):
        child = Learner.objects.get(pk=self.child_id)
        row = assign_lesson(child, "keys-v2", variation=0)
        family = Client()
        family.force_login(child.parent)
        family.post(reverse("manage", args=[child.pk]), {"action":"play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            page = browser.new_page()
            page.context.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
            # Tap the real audio output in headless Chrome and measure the rendered waveform.
            page.add_init_script("""
                window.cuePeaks = [];
                const connect = AudioNode.prototype.connect;
                AudioNode.prototype.connect = function(destination, ...rest) {
                  if (destination === this.context.destination) {
                    const meter = this.context.createAnalyser();
                    connect.call(this, meter);
                    const index = cuePeaks.push(0) - 1;
                    const data = new Float32Array(meter.fftSize);
                    const timer = setInterval(() => {
                      meter.getFloatTimeDomainData(data);
                      cuePeaks[index] = Math.max(cuePeaks[index], ...data);
                    }, 15);
                    setTimeout(() => clearInterval(timer), 700);
                  }
                  return connect.call(this, destination, ...rest);
                };
            """)
            page.goto(self.live_server_url + reverse("play", args=[row.pk]))
            toggle = page.get_by_role("checkbox", name="Answer sounds")
            expect(toggle).to_be_checked()
            page.keyboard.press("x")
            expect(page.locator(".retry-note")).to_be_visible()
            page.wait_for_function("cuePeaks.length === 1 && cuePeaks[0] > .01")
            page.keyboard.press("s")
            expect(page.locator(".answer-party")).to_be_visible()
            page.wait_for_function("cuePeaks.length === 2 && cuePeaks[1] > .01")
            expect(page.get_by_text("Step 2 of 5",exact=True)).to_be_visible()
            toggle.uncheck()
            # Move focus back to the activity after changing the audio control.
            page.locator('[data-screen-keyboard] summary').focus()
            page.keyboard.press("x")
            expect(page.locator(".retry-note")).to_be_visible()
            self.assertEqual(page.evaluate("cuePeaks.length"), 2)
            page.reload()
            expect(toggle).not_to_be_checked()
            toggle.check()
            page.get_by_role("button",name="Skip this question").click()
            expect(page.get_by_text("Step 3 of 5",exact=True)).to_be_visible()
            self.assertEqual(page.evaluate("cuePeaks.length"), 0)
            browser.close()

    def test_family_round_interactions(self):
        child = Learner.objects.get(pk=self.child_id)
        child.lesson_theme = "space"
        child.save(update_fields=["lesson_theme"])
        family = Client()
        family.force_login(child.parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    with browser.new_context(viewport={"width":width, "height":820}, has_touch=width == 375,
                                             color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid", "value":family.cookies["sessionid"].value,
                                          "url":self.live_server_url}])
                        self.exercise_family_rounds(ctx.new_page(), self.live_server_url, child.pk, width, theme)
            browser.close()

    def test_sentence_retry_history(self):
        child = Learner.objects.get(pk=self.child_id)
        row = assign_lesson(child, "sentence-v1", variation=4253)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action":"play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            page = browser.new_page()
            page.context.add_cookies([{"name":"sessionid", "value":device.cookies["sessionid"].value, "url":self.live_server_url}])
            page.goto(self.live_server_url + reverse("play", args=[row.pk]))
            self.exercise_sentence_retry(page,row.round_snapshot["items"][0])
            browser.close()
        row.refresh_from_db()
        self.assertEqual(row.step,1)
        self.assertEqual(row.retries,1)
        self.assertEqual(row.question_attempts.filter(step=0).count(),2)

    def exercise_family_rounds(self, page, base, child_id, width, theme):
        from pilot.practice import build_round
        from pilot.test_puzzles import winning_moves
        from pilot.themes import themed_round

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        def preview(key, variation, step=0):
            page.goto(base + reverse("preview", args=(child_id,key,step)) + f"?v={variation}")
            return themed_round(key, build_round(key,variation), "space", variation)["items"][step]
        def screen(label, selector):
            page.locator(selector).screenshot(path=self.out / f"round-{width}-{theme}-{label}.png")
            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        def center(locator):
            rect = locator.bounding_box()
            return {"x":rect["x"] + rect["width"]/2, "y":rect["y"] + rect["height"]/2}
        def drag(start, end):
            a, b = center(start), center(end)
            if width == 375:
                touch = page.context.new_cdp_session(page)
                for event, points in [("touchStart",[a]),("touchMove",[b]),("touchEnd",[])]:
                    touch.send("Input.dispatchTouchEvent", {"type":event,"touchPoints":points})
                touch.detach()
            else:
                page.mouse.move(**a)
                page.mouse.down()
                page.mouse.move(**b, steps=8)
                page.mouse.up()

        for key, variation in [("keys-v2",9385), ("number-keys-v2",8382)]:
            item = preview(key, variation)
            keys = page.locator("[data-screen-keyboard]")
            expect(keys.locator("button").first).to_be_hidden()
            keys.locator("summary").click()
            screen(key, "[data-screen-keyboard]")
            if key == "keys-v2":
                keys.locator("summary").click()
                page.keyboard.press(item["answer"].lower())
            else:
                keys.get_by_role("button",name=item["answer"],exact=True).click()
            expect(page.locator(".answer-party")).to_be_visible()
            if key == "number-keys-v2":
                expect(page.locator("[data-question-start]")).to_contain_text("Step 2")
                expect(page.locator("[data-screen-keyboard] button").first).to_be_visible()

        item = preview("shift-v1",2735,3)
        page.locator("[data-screen-keyboard] summary").click()
        shift = page.locator('[data-action="shift"]')
        shift.click()
        expect(shift).to_have_attribute("aria-pressed","false")
        page.keyboard.down("Shift")
        expect(shift).to_have_attribute("aria-pressed","true")
        page.keyboard.up("Shift")
        letter = page.locator(f'[data-letter="{item["answer"].lower()}"]')
        drag(shift, letter)
        expect(page.locator(".answer-party")).to_be_visible()

        if width == 375:
            preview("shift-v1",2735,3)
            page.locator("[data-screen-keyboard] summary").click()
            shift.scroll_into_view_if_needed()
            finger = {**center(shift), "id":1}
            other = {**center(letter), "id":2}
            touch = page.context.new_cdp_session(page)
            touch.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[finger]})
            expect(shift).to_have_attribute("aria-pressed","true")
            touch.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[finger,other]})
            touch.send("Input.dispatchTouchEvent", {"type":"touchEnd","touchPoints":[]})
            touch.detach()
            expect(page.locator(".answer-party")).to_be_visible()

        page.add_init_script("""window.tones = [];
            const ramp = AudioParam.prototype.exponentialRampToValueAtTime;
            AudioParam.prototype.exponentialRampToValueAtTime = function(value, when) {
                if (value > 1) tones.push(value);
                return ramp.call(this, value, when);
            };""")
        preview("arrow-maze-v1",9312)
        maze = page.locator("[data-maze]").get_attribute("data-maze")
        here = maze.index("B")
        for delta, arrow in [(1,"→"),(-1,"←"),(5,"↓"),(-5,"↑")]:
            there = here + delta
            if not (0 <= there < 25 and abs(there%5-here%5)<=1 and maze[there] != "#"):
                page.locator(f'[data-direction="{arrow}"]').click()
                expect(page.locator("[data-blocked]")).to_be_visible()
                break
        for delta, arrow in [(1,"→"),(-1,"←"),(5,"↓"),(-5,"↑")]:
            there = here + delta
            if 0 <= there < 25 and abs(there%5-here%5)<=1 and maze[there] != "#":
                page.locator(f'[data-direction="{arrow}"]').click()
                expect(page.locator('[name=tool_state]')).to_have_value(str(there))
                break

        self.assertEqual(len(page.evaluate("tones")),2)
        self.assertNotEqual(*page.evaluate("tones"))
        preview("river-v1",3290)
        expect(page.locator(".river-water")).to_have_attribute("d",page.locator("#ink").get_attribute("d"))
        screen("river","#trail")
        preview("harvest-v1",4961)
        pens = page.locator(".rabbit-pen")
        for pen in pens.all(): pen.locator("[data-feed]").click()
        pens.first.locator("[data-take]").click()
        expect(pens.first.locator("[data-take]")).to_be_disabled()
        expect(pens.nth(1).locator("output")).to_have_text("1")
        screen("harvest",".harvest")
        for key, variation, control in [("measure-v1",6181,"[data-action=count]"),("coins-v1",7328,"[data-coin]")]:
            preview(key,variation)
            page.locator(control).first.click()
            undo = page.get_by_role("button",name="Take one back")
            expect(undo).to_contain_text("−")
            undo.click()
            expect(undo).to_be_disabled()

        preview("sort-baskets-v1",80,1)
        piece = page.locator('[data-piece="0"]')
        bins = page.locator("[data-bin]")
        page.locator(".sort-board").scroll_into_view_if_needed()
        drag(piece, bins.first)
        expect(page.locator('[data-area="1"] [data-piece="0"]')).to_be_visible()
        drag(piece, bins.nth(1))
        expect(page.locator('[data-area="2"] [data-piece="0"]')).to_be_visible()
        screen("sort",".sort-board")
        piece.click()
        page.get_by_role("button",name="Take item out").click()
        expect(page.locator('[data-area="0"] [data-piece="0"]')).to_be_visible()

        for key, variation in [("digraphs-v1",2362), ("middle-sound-v1",1705)]:
            preview(key,variation)
            page.locator("[data-hear-word]").click()
            page.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
            self.assertAlmostEqual(page.locator(".word-station audio").evaluate("a=>a.playbackRate"),.82)
            self.assertEqual(page.locator("#directions-audio").evaluate("a=>a.playbackRate"),1)
        preview("snail-v1",7)
        expect(page.get_by_role("button",name="The bench")).to_be_visible()
        expect(page.get_by_role("button",name="The log")).to_contain_text("🪵")
        screen("landmarks","#activity")

        item = preview("sentence-v1",4253)
        self.exercise_sentence_retry(page,item)
        for key, step in [("water-works-v1",2),("train-tracks-v1",0)]:
            preview(key,14,step)
            page.locator("[data-run]").click()
            stop = page.locator(".is-stop")
            expect(stop).to_be_visible()
            encoded = list(map(int,page.locator("[name=tool_state]").input_value().split(",")))
            trace = encoded[page.locator("button.route-cell").count()+2:]
            self.assertNotIn(int(stop.get_attribute("data-index")), trace)
            if key == "water-works-v1":
                expect(page.locator(".route-console .retry-note")).to_be_visible()
                self.assertEqual(len(page.evaluate("tones")),2)

        item = preview("water-works-v1",14,1)
        for node,state in zip(page.locator("button.route-cell").all(), winning_moves(item["board"])[0], strict=True):
            if state and node.get_attribute("aria-label").startswith("empty space"):
                page.locator("[data-spare]").click()
            for _ in range(state): node.click()
        page.locator("[data-run]").click()
        expect(page.locator(".route-console .answer-party")).to_be_visible(timeout=12000)
        self.assertEqual(len(page.evaluate("tones")),3)
        screen("flow",".route-game")
        page.locator("[data-next]").click()
        expect(page.locator("[data-question-start]")).to_have_text("Step 3 of 5")
        preview("light-paths-v1",25)
        mirror = page.locator(".puzzle-mirror").first
        initial = mirror.evaluate("el=>getComputedStyle(el).transform")
        mirror.locator("xpath=ancestor::button").click()
        expect(mirror).not_to_have_css("transform",initial)
        screen("mirror",".route-grid")
        for step in (1,2):
            item = preview("bridges-v1",33,step)
            buttons = page.locator("button.route-cell")
            for node,state in zip(buttons.all(),winning_moves(item["board"])[0],strict=True):
                for _ in range(state): node.click()
            if step == 1:
                plank = page.locator(".bridge-plank i").bounding_box()
                self.assertGreater(plank["height"],1.8*buttons.first.bounding_box()["height"])
            screen(f"bridge-{step}",".route-grid")
            page.locator("[data-run]").click()
            expect(page.locator("[data-next]")).to_be_visible(timeout=12000)
        preview("bridges-v1",4)
        expect(page.locator(".bridge-rover")).to_be_visible()
        self.assertEqual(page.locator(".bridge-rover").evaluate("el=>el.style.transform"),"rotate(270deg)")
        self.assertEqual(errors,[])

    def exercise_sentence_retry(self, page, item):
        check = page.locator("[data-check]")
        words = item["answer"].split()
        def tile(word):
            return page.get_by_role("button", name=word, exact=True)
        tile(words[-1]).click()
        check.click()
        expect(page.locator("#answer-feedback")).to_contain_text("more words")
        for word in words[:-1]: tile(word).click()
        check.click()
        expect(page.locator("#answer-feedback")).to_contain_text("Check the word order")
        page.get_by_role("button", name="Start over").click()
        tile(words[-1]).click()
        page.get_by_role("button", name="Undo last word").click()
        for word in words: tile(word).click()
        check.click()
        expect(page.locator(".answer-party")).to_be_visible()
        expect(page.locator("[data-question-start]")).to_contain_text("Step 2")

    def test_family_lesson_feedback(self):
        parent = get_user_model().objects.get(username="reviewer")
        child = Learner.objects.create(parent=parent, nickname="Fern", lesson_theme="space")
        client = Client()
        client.force_login(parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    self.variant = f"feedback-{width}-{theme}"
                    with browser.new_context(viewport={"width":width, "height":820}, has_touch=width==375, color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid", "value":client.cookies["sessionid"].value, "url":self.live_server_url}])
                        page = ctx.new_page()
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        def preview(key, step=0):
                            page.goto(self.live_server_url + reverse("preview", args=[child.pk,key,step]))
                        def screen(name):
                            page.locator("article:has(#activity)").screenshot(path=self.out / f"{self.variant}-{name}.png")
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                        preview("shift-v1")
                        expect(page.locator("[data-keyboard]")).to_be_hidden()
                        page.get_by_text("Show on-screen keyboard").click()
                        expect(page.locator("[data-keyboard]")).to_be_visible()
                        preview("backspace-v1")
                        before = page.locator("[data-label] output").inner_text()
                        page.locator("#listen").click()
                        page.keyboard.press("Backspace")
                        expect(page.locator("[data-label] output")).to_have_text(before[:-1])
                        preview("arrow-maze-v1")
                        page.locator('[data-direction="↑"]').click()
                        expect(page.locator("[data-maze-status]")).to_contain_text("Blocked")
                        screen("wall")
                        preview("berry-basket-v1")
                        expect(page.locator(".cargo-bay-art")).to_be_visible()
                        hint = page.locator("[data-amount-hint]")
                        hint.locator("summary").click()
                        expect(hint).to_contain_text("Add more")
                        target = int(hint.get_attribute("data-target"))
                        for _ in range(target): page.locator("#add-berry").click()
                        expect(hint).to_contain_text("Just right")
                        page.locator("#add-berry").click()
                        expect(hint).to_contain_text("Take some out")
                        screen("cargo")
                        preview("coins-v1")
                        page.locator("[data-amount-hint] summary").click()
                        page.locator('[data-coin="5"]').click()
                        expect(page.locator("[data-hint-message]")).to_contain_text("5¢ on the counter")
                        screen("coins")
                        preview("tens-v1")
                        expect(page.locator(".ten-bag")).to_have_count(2)
                        expect(page.locator(".loose-pieces i")).to_have_count(3)
                        screen("bundles")
                        preview("sort-baskets-v1")
                        pieces = LESSONS["sort-baskets-v1"]["items"][0]["pieces"]
                        for i, piece in enumerate(pieces):
                            page.locator(f'[data-piece="{i}"]').click()
                            dest = piece["bin"] if i else 3-piece["bin"]
                            page.locator(f'[data-bin="{dest}"]').click()
                        page.locator("[data-sort-check]").click()
                        expect(page.locator(".retry-note")).to_be_visible()
                        page.locator('[data-piece="0"]').click()
                        page.locator("[data-unplace]").click()
                        expect(page.locator('[data-area="0"] [data-piece]')).to_have_count(1)
                        screen("sort")
                        page.locator("[data-sort-reset]").click()
                        expect(page.locator('[data-area="0"] [data-piece]')).to_have_count(len(pieces))
                        preview("number-dots-v1")
                        surface = page.locator(".dot-board")
                        surface.scroll_into_view_if_needed()
                        centers = surface.locator("[data-dot]").evaluate_all(
                            "els => els.map(e => { const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}; })")
                        if width == 375:
                            touch = ctx.new_cdp_session(page)
                            for i, point in enumerate(centers):
                                touch.send("Input.dispatchTouchEvent", {"type":"touchMove" if i else "touchStart","touchPoints":[point]})
                            touch.send("Input.dispatchTouchEvent", {"type":"touchEnd", "touchPoints":[]})
                        else:
                            page.mouse.move(**centers[0])
                            page.mouse.down()
                            for point in centers[1:]: page.mouse.move(**point,steps=6)
                            page.mouse.up()
                        expect(page.locator("[data-dot-finish]")).to_be_enabled()
                        screen("trail")
                        preview("digits-v2",4)
                        svg = page.locator("#trail")
                        expect(svg).to_have_attribute("data-shape","20")
                        svg.scroll_into_view_if_needed()
                        for _ in range(2):
                            points = svg.locator("#ink").evaluate("""p => {
                                const len=p.getTotalLength(), screen=p.getScreenCTM();
                                return Array.from({length:Math.ceil(len/3)+1},(_,i)=>{
                                    const pt=p.getPointAtLength(Math.min(len,i*3)).matrixTransform(screen);
                                    return {x:pt.x,y:pt.y}; }); }""")
                            page.mouse.move(**points[0])
                            page.mouse.down()
                            for point in points[1:]: page.mouse.move(**point)
                            page.mouse.up()
                            if _ == 0: screen("trace")
                        expect(page.locator(".answer-party")).to_be_visible()
                        self.assertEqual(errors, [])

            browser.close()

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

    def test_picture_cues_and_autoplay(self):
        parent = get_user_model().objects.get(username="reviewer")
        variants = []
        for device, width in (("phone",375), ("desktop",1200)):
            for theme in ("light", "dark"):
                child = Learner.objects.create(parent=parent, nickname=f"{device} {theme}")
                assign_lesson(child, "hear-number-v1", variation=1)
                family = Client()
                family.force_login(parent)
                variants.append((device, width, theme, child, family.cookies['sessionid'].value))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"),
                                         args=["--autoplay-policy=no-user-gesture-required"])
            for device, width, theme, child, cookie in variants:
                self.variant = f"{device}-{theme}"
                with browser.new_context(viewport={"width":width,"height":820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"url":self.live_server_url, "name":"sessionid", "value":cookie}])
                    page = ctx.new_page()
                    if theme == "dark":
                        page.add_init_script("""(() => {
                          const play = HTMLMediaElement.prototype.play;
                          HTMLMediaElement.prototype.play = function () {
                            if (this.id === 'directions-audio' && document.querySelector('[data-autoplay-directions]')
                                && !sessionStorage.getItem('qa-blocked-once')) {
                              sessionStorage.setItem('qa-blocked-once', '1');
                              return Promise.reject(new DOMException('Gesture required', 'NotAllowedError'));
                            }
                            return play.call(this);
                          };
                        })()""")
                    page.goto(self.live_server_url)
                    card = page.locator(f'[data-learner="{child.pk}"]')
                    card.locator(".learner-toggle").click()
                    box = card.get_by_role("checkbox", name=f"Play directions automatically for {child.nickname}")
                    expect(box).not_to_be_checked()
                    box.check()
                    card.get_by_role("button", name="Save lesson audio").click()
                    expect(box).to_be_checked()
                    card.locator(".lesson-audio-setting").screenshot(path=self.out / f"{self.variant}-audio-setting.png")
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk,"snail-v1",0]))
                    expect(page.locator("#activity")).not_to_have_attribute("data-autoplay-directions", "")
                    expect(page.locator(".question-heading .prompt-icon")).to_have_text("📖")
                    page.locator("main article").first.screenshot(path=self.out / f"{self.variant}-story-cues.png")
                    page.goto(self.live_server_url)
                    card.locator(".learner-toggle").click()
                    card.get_by_role("button", name=f"Open {child.nickname}’s garden").click()
                    page.get_by_role("link", name="Start lesson").click()
                    expect(page.locator("#activity")).to_have_attribute("data-autoplay-directions", "")
                    if theme == "dark":
                        expect(page.locator("#listen")).to_have_class(re.compile("needs-tap"))
                        self.capture(page, "blocked-audio")
                        page.get_by_role("button", name="Hear directions").click()
                    page.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
                    page.get_by_role("button", name="Stop audio").click()
                    expect(page.locator("#stop-audio")).to_be_hidden()
                    page.get_by_role("button", name="Hear directions").click()
                    page.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                    self.capture(page, "spoken-question")
                    page.get_by_role("button", name="Skip this question").click()
                    expect(page.get_by_text("Step 2 of 5")).to_be_visible()
                    page.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
                    self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
            browser.close()

    def test_preview_returns_to_catalog_position(self):
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        cases = [(width, theme, Learner.objects.create(parent=parent, nickname="Fern"))
                 for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, learner in cases:
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value, "url": self.live_server_url}])
                    page = ctx.new_page()
                    url = self.live_server_url + reverse("library", args=[learner.pk])
                    page.goto(url + "?category=Numbers+%26+patterns&participation=Independent&browse=schedule&day=2026-12-03")
                    page.locator(".tier-key summary").click()
                    cards = page.locator("#available-lessons [data-lesson]")
                    index = cards.count() // 2
                    card = cards.nth(index)
                    key = card.get_attribute("id")
                    neighbor = cards.nth(index + 1).get_attribute("id")
                    card.evaluate("e => scrollBy(0, e.getBoundingClientRect().top - 100)")
                    top = card.bounding_box()["y"]
                    self.assertGreater(page.evaluate("scrollY"), 500)
                    link = card.locator("[data-preview]")
                    link.click()
                    page.go_back()
                    expect(link).to_be_focused()
                    self.assertAlmostEqual(card.bounding_box()["y"], top, delta=2)
                    link.press("Enter")
                    page.get_by_role("link", name="Shuffle round").click()
                    page.locator(".preview-steps a").last.click()
                    page.get_by_role("button", name="Skip this question").click()
                    expect(page.get_by_role("heading", name="Preview complete")).to_be_visible()
                    page.get_by_role("link", name="Back to lesson library").click()
                    expect(page.locator(f"#{key} [data-preview]")).to_be_focused()
                    self.assertAlmostEqual(card.bounding_box()["y"], top, delta=2)
                    expect(page.get_by_label("Subject")).to_have_value("Numbers & patterns")
                    expect(page.get_by_label("Adult involvement")).to_have_value("Independent")
                    self.assertIn("day=2026-12-03", page.url)
                    self.assertTrue(page.locator(".tier-key").evaluate("e => e.open"))
                    page.screenshot(path=self.out / f"catalog-return-{width}-{theme}.png")
                    link.click()
                    page.get_by_role("button", name="Add to Fern’s queue").click()
                    expect(page.locator("[data-queue-status]")).to_contain_text("added")
                    page.get_by_role("link", name="Back to lesson library").click()
                    expect(page.locator(f"#{key}")).to_have_count(0)
                    expect(page.locator(f"#{neighbor} [data-preview]")).to_be_focused()
                    self.assertAlmostEqual(page.locator(f"#{neighbor}").bounding_box()["y"], top, delta=2)
                    page.goto(url)
                    self.assertEqual(page.evaluate("scrollY"), 0)
            browser.close()

    def test_shuffle_preview_and_assign(self):
        family = Client()
        parent = get_user_model().objects.get(username="reviewer")
        family.force_login(parent)
        cases = [(device, width, theme, Learner.objects.create(parent=parent, nickname="Fern"))
                 for device, width in (("phone", 375), ("desktop", 1200)) for theme in ("light", "dark")]
        assigned = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for device, width, theme, child in cases:
                self.variant = f"{device}-{theme}"
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name":"sessionid", "value":family.cookies["sessionid"].value,
                                     "url":self.live_server_url}])
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk, "water-works-v1", 0]) + "?v=0")
                    page.get_by_role("link", name="Shuffle round").click()
                    variation = int(page.locator('input[name="variation"]').input_value())
                    self.assertGreater(variation, 0)
                    game = page.locator(".route-game")
                    game.locator("[data-hint]").click()
                    expect(game.locator(".is-hint")).to_be_visible()
                    self.capture(page, "shuffled-route")
                    page.get_by_role("button", name="Add to Fern’s queue").click()
                    expect(page.locator("[data-queue-status]")).not_to_be_empty()
                    page.get_by_role("link", name="Schedule this round").click()
                    expect(page.get_by_role("dialog")).to_contain_text(f"preview round {variation+1}")
                    page.get_by_role("button", name="Schedule lesson").click()
                    expect(page.get_by_role("dialog")).not_to_be_visible()
                    assigned.append((child, variation))
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk, "letters-v1", 0]) + "?v=1073")
                    lengths = page.locator("#trail").evaluate("""svg => {
                        const path = document.createElementNS(svg.namespaceURI, 'path');
                        return [...'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'].map(ch => {
                            const shape = traceShapes[ch];
                            path.setAttribute('d', Array.isArray(shape) ? shape.join(' ') : shape);
                            return path.getTotalLength();
                        });
                    }""")
                    self.assertTrue(all(length > 0 for length in lengths))
                    self.capture(page, "expanded-tracing")
            browser.close()
        for child, variation in assigned:
            self.assertEqual(child.assignment_set.get().variation, variation)
            self.assertEqual(child.lessonplan_set.get().first_variation, variation)

    def test_envelope_trails(self):
        family = Client()
        family.force_login(get_user_model().objects.get(username="reviewer"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value, "url": self.live_server_url}])
                        page = ctx.new_page()
                        for key, variation, step in (("letter-dots-v1", 34, 4), ("number-dots-v1", 32, 3)):
                            page.goto(self.live_server_url + reverse("preview", args=[self.child_id, key, step]) + f"?v={variation}")
                            board = page.locator(".garden-tool")
                            dots = board.locator("[data-dot]")
                            if key == "letter-dots-v1":
                                self.assertEqual(dots.all_text_contents(), list("EFGHIJK"))
                            line = board.locator("[data-dot-line]")
                            for i, dot in enumerate(dots.all()):
                                dot.click()
                                if i < 6:
                                    self.assertEqual(len(line.get_attribute("points").split()), i + 1)
                            points = line.get_attribute("points").split()
                            self.assertEqual(points[-3:], ["50,56", points[0], points[5]])
                            self.assertEqual({points[0], points[5]}, {"12,24", "88,24"})
                            self.assertEqual({points[2], points[3]}, {"12,76", "88,76"})
                            expect(board.locator("[data-dot-status]")).to_have_text("You drew an envelope!")
                            expect(board.locator("[data-dot-finish]")).to_be_enabled()
                            if key == "letter-dots-v1":
                                board.screenshot(path=self.out / f"envelope-{width}-{theme}.png")
            browser.close()

    def test_exploration_lessons(self):
        from pilot.explorations import EXPLORATIONS
        from pilot.practice import build_round

        child = Learner.objects.get(pk=self.child_id)
        account = Client()
        account.force_login(child.parent)
        assignment = assign_lesson(child, "number-dots-v1", variation=2)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for viewport, width in (("phone", 375), ("desktop", 1200)):
                for theme in ("light", "dark"):
                    self.variant = f"{viewport}-{theme}"
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid", "value":account.cookies["sessionid"].value,
                                         "url":self.live_server_url}])
                        page = ctx.new_page()
                        for key in EXPLORATIONS:
                            step = 3 if key == "money-total-v1" else 0
                            page.goto(self.live_server_url + reverse("preview", args=[child.pk, key, step]))
                            board = page.locator(".garden-tool")
                            item = build_round(key, 0)["items"][step]
                            expect(page.locator("#prompt")).to_have_text(item["prompt"])
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"), key)
                            if "dots" in item:
                                dots = board.locator("[data-dot]")
                                dots.nth(2).click()
                                expect(page.locator(".retry-note")).to_be_visible()
                                for dot in dots.all():
                                    dot.press("Space")
                                expect(board.locator("[data-dot-finish]")).to_be_enabled()
                            elif key == "hear-number-v1":
                                page.get_by_role("button", name="Hear the number").click()
                                page.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                            elif "pieces" in item:
                                for index, piece in enumerate(item["pieces"]):
                                    board.locator(f'[data-piece="{index}"]').click()
                                    board.locator(f'[data-bin="{piece["bin"]}"]').click()
                                expect(board.locator("[data-sort-check]")).to_be_enabled()
                            board.screenshot(path=self.out / f"{self.variant}-explore-{key}.png")
                            if key == "inside-outside-v1":
                                board.locator(f'button[value="{item["answer"]}"]').click()
                                expect(page.locator(".preview-steps [aria-current]")).to_have_text("2")
            page = browser.new_page(viewport={"width":320,"height":700}, has_touch=True)
            page.context.add_cookies([{"name":"sessionid","value":device.cookies["sessionid"].value,"url":self.live_server_url}])
            page.goto(self.live_server_url + reverse("play", args=[assignment.pk]))
            for dot in page.locator("[data-dot]").all():
                dot.tap()
            page.get_by_role("button", name="Finish picture").tap()
            expect(page.get_by_text("Step 2 of 5")).to_be_visible()
            browser.close()

    def test_feedback_resolution(self):
        from pilot.models import LessonFeedback

        reviewer = Client()
        reviewer.force_login(get_user_model().objects.get(username="reviewer"))
        writer = get_user_model().objects.create_user("family-tester")
        family = Client()
        family.force_login(writer)
        cases = [(width, theme, LessonFeedback.objects.create(
            parent=writer, lesson="coins-v1", step=1, variation=7, kind="confusing", note=f"Coin hint needs another look ({width}, {theme})."))
            for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, note in cases:
                self.variant = f"resolution-{width}-{theme}"
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as team, \
                     browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as parent:
                    for ctx, client in [(team, reviewer), (parent, family)]:
                        ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": self.live_server_url}])
                    review, history = team.new_page(), parent.new_page()
                    review.goto(self.live_server_url + reverse("dashboard") + "?lesson=coins-v1&flag=confusing")
                    expect(review.get_by_role("combobox", name="Resolution", exact=True)).to_have_value("open")
                    card = review.locator(f"#note-{note.pk}")
                    card.get_by_role("button", name="Mark resolved").click()
                    expect(card).to_have_count(0)
                    review.get_by_role("combobox", name="Resolution", exact=True).select_option("resolved")
                    review.get_by_role("button", name="Apply filters").click()
                    expect(card).to_contain_text("Marked resolved")
                    review.locator("form[method=get]").screenshot(path=self.out / f"{self.variant}-filter.png")
                    return_url = review.url.split("#")[0] + f"#note-{note.pk}"
                    card.get_by_role("link", name="Try this round again").click()
                    expect(review.locator(".preview-steps [aria-current]")).to_have_text("2")
                    review.get_by_role("link",name="Back to feedback entry").first.click()
                    expect(review).to_have_url(return_url)
                    history.goto(self.live_server_url + reverse("feedback_history") + f"#note-{note.pk}")
                    entry = history.locator(f"#note-{note.pk}")
                    entry.get_by_role("link", name="Try this round again").click()
                    expect(history.locator(".preview-steps [aria-current]")).to_have_text("2")
                    expect(history.get_by_text("Feedback preview · Round 8")).to_be_visible()
                    history.locator("[data-coin]").first.click()
                    history.get_by_role("button",name="Take one back").click()
                    original = history.locator("#original-feedback")
                    original.get_by_text("Reopen feedback", exact=True).click()
                    original.get_by_label("What still needs work?", exact=False).fill("It happens again after taking a coin back.")
                    original.screenshot(path=self.out / f"{self.variant}-parent.png")
                    original.get_by_role("button", name="Reopen for review").click()
                    expect(entry).to_contain_text("Open · Awaiting review")
                    expect(entry).to_contain_text("It happens again after taking a coin back.")
                    review.reload()
                    expect(card).to_have_count(0)
                    expect(review.get_by_text("No feedback matches these filters.")).to_be_visible()
                    review.get_by_role("combobox", name="Resolution", exact=True).select_option("open")
                    review.get_by_label("Review status").select_option("unread")
                    review.get_by_role("button", name="Apply filters").click()
                    expect(card).to_contain_text("It happens again after taking a coin back.")
                    card.screenshot(path=self.out / f"{self.variant}-reopened.png")
                    for page in (history, review):
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
            browser.close()

    def test_technical_dashboard(self):
        from unittest.mock import patch

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for device, width in (("phone", 375), ("desktop", 1200)):
                for theme in ("light", "dark"):
                    self.variant = f"{device}-{theme}"
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        page = ctx.new_page()
                        page.goto(self.live_server_url + reverse("login"))
                        page.locator("[name=username]").fill("reviewer")
                        page.locator("[name=password]").fill("garden-qa-only")
                        page.get_by_role("button", name="Sign in", exact=True).click()
                        page.get_by_role("link", name="Admin dashboard").click()
                        page.get_by_role("link", name="Technical", exact=True).click()
                        expect(page.locator('.ops-grid div').filter(has=page.get_by_text("Fully completed", exact=True)).locator("dd")).to_contain_text("2")
                        expect(page.locator(".ops-week li")).to_have_count(7)
                        self.capture(page, "technical")
                        with patch("pilot.operations.cpu_ticks", side_effect=OSError):
                            page.get_by_role("link", name="Refresh snapshot").click()
                            expect(page.locator(".ops-grid dd").first).to_contain_text("Unavailable")
                        page.get_by_role("link", name="Lesson review", exact=True).click()
                        expect(page.get_by_role("heading", name="Lesson review")).to_be_visible()
            browser.close()

    def test_assignment_history(self):
        from datetime import timedelta

        child = Learner.objects.get(pk=self.child_id)
        new_learner = Learner.objects.create(parent=child.parent, nickname="Pip")
        recent = timezone.now() - timedelta(days=7)
        child.assignment_set.update(completed=recent, assigned_at=recent)
        round_row = assign_lesson(child, "keys-v2", 1)
        player = Client()
        player.force_login(child.parent)
        player.post(reverse("manage", args=[child.pk]), {"action": "play"})
        play = reverse("play", args=[round_row.pk])
        player.get(play)
        item = round_row.round_snapshot["items"][0]
        player.post(play, {"step": 0, "answer": "?", "active_ms": 1800})
        player.post(play, {"step": 0, "answer": item["answer"], "active_ms": 4000})
        for step in range(1, len(round_row.round_snapshot["items"])):
            player.post(play, {"step": step, "action": "skip"})

        family = Client()
        family.force_login(child.parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for device, width in (("phone", 375), ("desktop", 1200)):
                for theme in ("light", "dark"):
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        self.variant = f"{device}-{theme}"
                        ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value,
                                         "url": self.live_server_url}])
                        page = ctx.new_page()
                        page.goto(self.live_server_url)
                        page.locator(f'[data-learner="{new_learner.pk}"] .learner-menu summary').click()
                        page.locator(f'[data-learner="{new_learner.pk}"]').get_by_role("link", name="Assignment history").click()
                        expect(page.get_by_role("heading", name="No assignments yet")).to_be_visible()
                        self.capture(page, "history-empty")
                        page.goto(self.live_server_url + reverse("library", args=[child.pk]))
                        card = page.locator('[data-lesson="keys-v2"]')
                        card.screenshot(path=self.out / f"{self.variant}-history-card.png")
                        card.get_by_role("link", name="Last completed 7 days ago").click()
                        expect(page.get_by_role("combobox", name="Lesson", exact=True)).to_have_value("keys-v2")
                        expect(page.locator(".history-list li")).to_have_count(3)
                        self.capture(page, "history-rounds")
                        details = page.locator(".history-questions").first
                        details.locator("summary").click()
                        expect(details).to_contain_text("Try 1 · Incorrect · ?")
                        expect(details).to_contain_text("Try 2 · Correct")
                        expect(details).to_contain_text("Skipped")
                        details.locator("summary").evaluate('el => el.scrollIntoView({block: "start"})')
                        page.screenshot(path=self.out / f"{self.variant}-history-attempts.png")
                        page.get_by_role("combobox", name="Status", exact=True).select_option("Removed")
                        page.get_by_role("button", name="Apply filters").click()
                        expect(page.get_by_role("heading", name="No matching assignments")).to_be_visible()
                        page.get_by_role("link", name="Clear filters").click()
                        expect(page.locator(".history-status").get_by_text("Finished with skips")).to_be_visible()
            browser.close()

    def test_open_lesson_refreshes_an_older_player(self):
        child = Learner.objects.get(pk=self.child_id)
        row = assign_lesson(child, "sounds-v1", 0)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            page = browser.new_page()
            page.context.add_cookies([{"name": "sessionid", "value": device.cookies["sessionid"].value,
                                       "url": self.live_server_url}])
            def old_page(route):
                response = route.fetch()
                body = re.sub(r'activity\.js\?v=[^"]+', "activity.js?v=prior-release", response.text(), count=1)
                route.fulfill(response=response, body=body)
            page.route(self.live_server_url + "/", old_page, times=1)
            page.goto(self.live_server_url)
            page.evaluate("window.previousPlayer = true")
            page.get_by_role("link", name="Start lesson").click()
            expect(page).to_have_url(self.live_server_url + reverse("play", args=[row.pk]))
            self.assertFalse(page.evaluate("Boolean(window.previousPlayer)"))
            page.get_by_role("button", name="Hear directions").click()
            page.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
            browser.close()

    def test_animals_sorting_letters_and_appearance(self):
        family = Client()
        parent = get_user_model().objects.get(username="reviewer")
        family.force_login(parent)
        variants = [(width, theme, Learner.objects.create(parent=parent, nickname="Kit"))
                    for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, child in variants:
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value,
                                      "url": self.live_server_url}])
                    self.variant = f"discovery-{width}-{theme}"
                    page = ctx.new_page()
                    def preview(key, step=0):
                        page.goto(self.live_server_url + reverse("preview", args=[child.pk, key, step]))
                    page.goto(self.live_server_url)
                    card = page.locator(f'article[data-learner="{child.pk}"]')
                    card.locator(".learner-toggle").click()
                    card.locator(".look-editor summary").click()
                    editor = card.locator("[data-look-form]")
                    editor.locator("[name=accent]").fill("#7955c2")
                    editor.locator("[name=font]").select_option("mono")
                    editor.screenshot(path=self.out / f"{self.variant}-editor.png")
                    editor.get_by_role("button", name="Save appearance").click()
                    preview("animal-calls-v1")
                    expect(page.locator("main")).to_have_attribute("data-font", "mono")
                    expect(page.locator("main")).to_have_attribute("data-accent", "")
                    page.get_by_role("button", name="Hear animal call").click()
                    page.wait_for_function("document.querySelector('[data-call-audio]').currentTime > 0")
                    page.locator(".garden-tool").screenshot(path=self.out / f"{self.variant}-animals.png")
                    animal = LESSONS["animal-calls-v1"]["items"][0]["answer"]
                    page.get_by_role("button", name=animal.capitalize(), exact=True).click()
                    expect(page.locator(".preview-steps [aria-current]")).to_have_text("2")
                    preview("animal-lookout-v1")
                    expect(page.locator(".picture-choices button")).to_have_count(3)
                    preview("animal-words-v1")
                    page.locator("[data-hear-word]").click()
                    page.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                    expect(page.locator(".animal-fragment")).to_contain_text("_")
                    page.locator(".animal-fragment").screenshot(path=self.out / f"{self.variant}-animal-word.png")
                    preview("alphabet-gap-v1")
                    expect(page.locator(".display")).to_contain_text("＿")
                    page.locator(".display").screenshot(path=self.out / f"{self.variant}-alphabet.png")
                    preview("sort-baskets-v1")
                    pieces = LESSONS["sort-baskets-v1"]["items"][0]["pieces"]
                    check = page.locator("[data-sort-check]")
                    expect(check).to_be_disabled()
                    for i, piece in enumerate(pieces):
                        page.locator(f'[data-piece="{i}"]').press("Space")
                        page.locator(f'[data-bin="{piece["bin"]}"]').click()
                    page.locator(".sort-board").screenshot(path=self.out / f"{self.variant}-baskets.png")
                    check.click()
                    expect(page.locator(".preview-steps [aria-current]")).to_have_text("2")
                    preview("my-letters-v1")
                    page.get_by_label("Letters to practice").fill("R I O N")
                    page.get_by_role("button", name="Preview these letters").click()
                    expect(page.get_by_label("Letters to practice")).to_have_value("RION")
                    page.locator(".preview-tools").screenshot(path=self.out / f"{self.variant}-letters.png")
                    page.get_by_role("button", name="Add to Kit’s queue").click()
                    expect(page.locator("[data-queue-status]")).to_contain_text("added to Kit")
                    self.capture(page, "custom-round")
            browser.close()
        for _, _, child in variants:
            self.assertEqual(child.assignment_set.get().round_snapshot["letters"], "RION")

    def test_paint_tray(self):
        child = Learner.objects.get(pk=self.child_id)
        family = Client()
        family.force_login(child.parent)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        variants = [(width, theme, assign_lesson(child, "mix-paint-v1", 0))
                    for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, row in variants:
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                    def login(client):
                        ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value,
                                          "url": self.live_server_url}])
                    self.variant = f"paint-{width}-{theme}"
                    login(family)
                    page = ctx.new_page()
                    for key in ("match-paint-v1", "name-paint-v1"):
                        page.goto(self.live_server_url + reverse("preview", args=[child.pk, key, 0]))
                        item = LESSONS[key]["items"][0]
                        if key == "name-paint-v1":
                            page.get_by_role("button", name="Hear directions").click()
                            page.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
                        page.locator(".paint-studio").screenshot(path=self.out / f"{self.variant}-{key}.png")
                        page.get_by_role("button", name=item["answer"].capitalize() + " paint", exact=True).click()
                        expect(page.locator(".preview-steps [aria-current]")).to_have_text("2")
                    login(device)
                    page.goto(self.live_server_url + reverse("play", args=[row.pk]))
                    item = LESSONS["mix-paint-v1"]["items"][0]
                    first, second = next((r["first"], r["second"]) for r in item["recipes"]
                                         if r["result"]["name"] == item["answer"])
                    check = page.get_by_role("button", name="Check my mix")
                    expect(check).to_be_disabled()
                    pot = page.locator(f'[data-pigment="{first}"]')
                    pot.click()
                    pot.click()
                    check.click()
                    expect(page.locator("#answer-feedback .retry-note")).to_be_visible()
                    page.get_by_role("button", name="Undo").click()
                    expect(check).to_be_disabled()
                    page.locator(f'[data-pigment="{second}"]').press("Space")
                    expect(page.locator("[data-mixture] output")).to_have_text(item["answer"])
                    page.locator(".paint-studio").screenshot(path=self.out / f"{self.variant}-mix.png")
                    self.capture(page, "lesson")
                    check.click()
                    expect(page.get_by_text("Step 2 of 5")).to_be_visible()
            browser.close()
        for _, _, row in variants:
            self.assertEqual(row.samples.get(step=0).score, 0)

    def test_child_memory_retry_keeps_next_pair(self):
        child = Learner.objects.get(pk=self.child_id)
        row = assign_lesson(child, "letter-memory-v1", variation=0)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            page = browser.new_page()
            page.context.add_cookies([{"url": self.live_server_url, "name": "sessionid",
                                       "value": device.cookies["sessionid"].value}])
            page.goto(self.live_server_url + reverse("play", args=[row.pk]))
            first = page.locator('[data-card="0"]')
            second = page.locator('[data-card="1"]')
            first.first.click()
            second.first.click()
            expect(page.locator('[data-face="down"]')).to_have_count(4)
            first.first.click()
            second.first.click()
            # A third card can start the next turn before the automatic cover.
            first.last.click()
            first.first.click()
            second.first.click()
            second.last.click()
            expect(page.locator('[data-face="matched"]')).to_have_count(4)
            page.get_by_role("button", name="Continue").click()
            expect(page.get_by_text("Step 2 of 5")).to_be_visible()
            browser.close()
        row.refresh_from_db()
        self.assertEqual((row.step, row.retries), (1, 0))

    def test_card_table_and_seesaw(self):
        child = Learner.objects.get(pk=self.child_id)
        family = Client()
        family.force_login(child.parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    self.variant = f"table-{width}-{theme}"
                    with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as ctx:
                        ctx.add_cookies([{"url": self.live_server_url, "name": "sessionid",
                                          "value": family.cookies["sessionid"].value}])
                        page = ctx.new_page()
                        def preview(key, step):
                            page.goto(self.live_server_url + reverse("preview", args=[child.pk, key, step]))
                        preview("sound-memory-v1", 1)
                        first, second = [
                            page.locator(f'[data-card="{n}"]') for n in (0, 1)]
                        first.first.click()
                        page.wait_for_function("document.querySelector('[data-card-audio]').currentTime > 0")
                        second.first.press("Space")
                        expect(page.locator("[data-cover]")).to_be_visible()
                        page.locator("[data-clues]").check()
                        self.capture(page, "memory-miss")
                        page.locator(".garden-tool").screenshot(path=self.out / f"{self.variant}-memory-miss-board.png")
                        expect(page.locator('[data-face="down"]')).to_have_count(4)
                        expect(page.locator("[data-cover]")).to_be_hidden()
                        expect(page.locator('[name="tool_state"]')).to_have_value("")
                        for pair in (first, second):
                            pair.first.click()
                            pair.last.click()
                        page.locator("[data-finish]").click()
                        expect(page.locator(".preview-steps [aria-current]")).to_have_text("3")
                        preview("letter-memory-v1", 4)
                        cards = page.locator("[data-card]")
                        for index in (0, 1):
                            page.locator('[data-card="0"]').nth(index).click()
                        for pair in (1, 2):
                            page.locator(f'[data-card="{pair}"]').first.click()
                        expect(page.locator('[data-face="up"]')).to_have_count(2)
                        expect(page.locator('[data-face="up"]')).to_have_count(0)
                        expect(page.locator('[data-face="matched"]')).to_have_count(2)
                        expect(cards.locator(".card-back:visible")).to_have_count(6)
                        self.capture(page, "words")
                        page.locator(".garden-tool").screenshot(path=self.out / f"{self.variant}-words-board.png")
                        preview("seesaw-v1", 1)
                        target = page.locator(".seesaw").get_attribute("data-target")
                        weight = page.locator(f'[data-weight="{target}"]')
                        weight.click()
                        expect(page.locator("[data-table-status]")).to_contain_text("Balanced!")
                        weight.click()
                        expect(page.locator("[data-weigh]")).to_be_disabled()
                        weight.press("Space")
                        self.capture(page, "seesaw")
                        page.locator(".garden-tool").screenshot(path=self.out / f"{self.variant}-seesaw-board.png")
                        page.locator("[data-weigh]").click()
                        expect(page.locator(".preview-steps [aria-current]")).to_have_text("3")
            browser.close()

    def test_logic_puzzles(self):
        child = Learner.objects.get(pk=self.child_id)
        child.lesson_theme = "space"
        child.save()
        family = Client()
        family.force_login(child.parent)
        device = Client()
        device.force_login(child.parent)
        device.post(reverse("manage", args=[child.pk]), {"action": "play"})
        variants = [(width, theme, assign_lesson(child, "water-works-v1", 0))
                    for width in (1200, 375) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, row in variants:
                self.variant = f"route-{width}-{theme}"
                with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme,
                                         has_touch=width == 375) as ctx:
                    def sign_in(client):
                        ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value,
                                          "url": self.live_server_url}])
                    sign_in(device)
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("play", args=[row.pk]))
                    game = page.locator(".route-game")
                    game.locator("[data-run]").click()
                    expect(game.locator(".is-stop")).to_be_visible()
                    game.locator("[data-hint]").click()
                    expect(game.locator(".is-hint")).to_be_visible()
                    self.capture(page, "hint")
                    valve = game.get_by_role("button", name=re.compile("closed valve"))
                    valve.focus()
                    valve.press("Space")
                    game.locator("[data-undo]").click()
                    expect(valve).to_be_visible()
                    valve.click()
                    game.locator("[data-run]").click()
                    expect(game.locator("[data-next]")).to_be_visible()
                    self.capture(page, "water")
                    if width == 1200 and theme == "light":
                        with browser.new_context() as viewer:
                            viewer.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value,
                                                 "url": self.live_server_url}])
                            mirror = viewer.new_page()
                            mirror.goto(self.live_server_url + reverse("coview"))
                            expect(mirror.locator(".route-game .is-arrived")).to_be_visible(timeout=15000)
                    game.locator("[data-next]").click()
                    expect(page.locator(".route-heading")).to_contain_text("Around the bend")
                    sign_in(family)
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk, "train-tracks-v1", 1]))
                    spare = game.locator("[data-spare]")
                    socket = game.get_by_role("button", name=re.compile("empty space"))
                    if width == 375:
                        spare.tap()
                        socket.tap()
                    else:
                        spare.drag_to(socket)
                    bend = game.get_by_role("button", name=re.compile("bend,"))
                    expect(bend).to_be_visible()
                    game.locator("[data-reset]").click()
                    expect(socket).to_be_visible()
                    spare.click()
                    socket.click()
                    for _ in range(3):
                        bend.click()
                    game.locator("[data-run]").click()
                    game.locator("[data-stop]").click()
                    expect(game.locator(".route-message")).to_contain_text("Paused")
                    game.locator("[data-run]").click()
                    expect(game.locator("[data-next]")).to_be_visible()
                    self.capture(page, "station")
            browser.close()
        for _, _, row in variants:
            row.refresh_from_db()
            self.assertEqual(row.step, 1)
            self.assertEqual(row.samples.get(step=0).puzzle_help, 1)

    def test_new_lessons_and_library_queue(self):
        parent = get_user_model().objects.get(username="reviewer")
        login = Client()
        login.force_login(parent)
        for size, width in (("desktop", 1200), ("phone", 375)):
            for theme in ("light", "dark"):
                self.variant = f"{size}-{theme}"
                child = Learner.objects.create(parent=parent, nickname="Pip")
                device = Client()
                device.force_login(parent)
                device.post(reverse("manage", args=[child.pk]), {"action": "play"})
                for key in ("middle-sound-v1", "digraphs-v1", "ten-v1"):
                    assign_lesson(child, key, 0)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
                    with self.subTest(size=size, theme=theme), browser.new_context(
                        viewport={"width": width, "height": 820}, color_scheme=theme
                    ) as family, browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as learner:
                        for ctx, signed_in in ((family, login), (learner, device)):
                            ctx.add_cookies([{"name": "sessionid", "value": signed_in.cookies["sessionid"].value,
                                              "url": self.live_server_url}])
                        learner.add_init_script("""Object.defineProperty(window, "speechSynthesis", {value: undefined})""")
                        page, kid = family.new_page(), learner.new_page()
                        library = self.live_server_url + reverse("library", args=[child.pk])
                        page.goto(library)
                        card = page.locator('[data-lesson="lowercase-v1"]')
                        page.evaluate("window.sameLibrary = true")
                        card.get_by_role("button").click()
                        expect(card).to_have_count(0)
                        self.assertTrue(page.evaluate("window.sameLibrary && scrollY > 0"))
                        page.screenshot(path=self.out / f"{self.variant}-library-after-add.png")
                        page.get_by_label("Subject").select_option("Numbers & patterns")
                        page.get_by_label("Adult involvement").select_option("Parent required")
                        page.get_by_role("button", name="Filter lessons").click()
                        page.get_by_role("link", name="Schedule all (2)").click()
                        expect(page.get_by_role("dialog")).to_contain_text("2 selected lessons")
                        page.get_by_role("button", name="Schedule 2 lessons").click()
                        expect(page.get_by_role("dialog")).not_to_be_visible()
                        expect(page.locator("[data-queue-status]")).to_contain_text("2 lessons scheduled for Pip")
                        page.get_by_role("button", name="Add all (2)").click()
                        expect(page.locator("[data-empty]")).to_be_visible()
                        self.capture(page, "library-filter-queued")
                        kid.goto(self.live_server_url)
                        expect(kid.get_by_role("link", name="Start lesson")).to_have_count(6)
                        page.goto(library + "middle-sound-v1/preview/0/?v=1")
                        page.get_by_role("button", name="Hear directions").click()
                        page.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
                        page.get_by_role("button", name="Hear the word").click()
                        page.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                        self.capture(page, "piper-preview")
                        page.goto(library + "case-match-v1/preview/0/")
                        page.get_by_role("button", name="Add to Pip’s queue").click()
                        expect(page.locator(".preview-tools")).to_contain_text("added to Pip’s queue")
                        expect(page.get_by_role("heading", name="Match big & small letters")).to_be_visible()
                        page.goto(self.live_server_url + reverse("coview"))
                        page.get_by_label("Show", exact=True).select_option(str(child.pk))
                        tile = page.locator(f'[data-child="{child.pk}"]')
                        for key in ("case-match-v1", "middle-sound-v1", "digraphs-v1", "lowercase-v1", "ten-v1", "harvest-v1"):
                            kid.goto(self.live_server_url)
                            kid.locator("article").filter(has=kid.get_by_role("heading", name=LESSONS[key]["title"], exact=True)).get_by_role("link").click()
                            item = LESSONS[key]["items"][0]
                            expect(tile.locator("h3")).to_have_text(item["prompt"], timeout=10000)
                            if key in ("middle-sound-v1", "digraphs-v1"):
                                kid.get_by_role("button", name="Hear the word").click()
                                kid.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                                expect(tile).to_contain_text("Spoken word · " + item["word"])
                            if key == "ten-v1":
                                cells = kid.locator(".ten-frame span")
                                expect(cells).to_have_count(10)
                                expect(tile.locator(".ten-frame .planted")).to_have_count(item["seeds"])
                                tops = cells.evaluate_all("cells => cells.map(cell => cell.offsetTop)")
                                self.assertEqual(len(set(tops[:5])), 1)
                                self.assertEqual(len(set(tops[5:])), 1)
                                self.assertGreater(tops[5], tops[0])
                                kid.locator('#activity button[value="4"]').click()
                                expect(kid.locator(".retry-note")).to_be_visible()
                            if key == "harvest-v1":
                                for _ in range(3):
                                    for n in (1, 2):
                                        kid.get_by_role("button", name=f"Give a carrot to rabbit {n}").click()
                                expect(tile.locator(".rabbit-pen output").first).to_have_text("3")
                            kid.locator("article").screenshot(path=self.out / f"{self.variant}-{key}.png")
                            self.assertFalse(kid.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            if key == "lowercase-v1":
                                expect(tile.locator(".soil-lines line")).to_have_count(3)
                                points = kid.locator("#guide").evaluate("""p => {
                                  const len = p.getTotalLength(), n = Math.ceil(len / 5);
                                  return Array.from({length:n+1}, (_,i) => {
                                    const at = p.getPointAtLength(len*i/n).matrixTransform(p.getScreenCTM());
                                    return [at.x, at.y];
                                  });
                                }""")
                                kid.mouse.move(*points[0])
                                kid.mouse.down()
                                for point in points[1:]:
                                    kid.mouse.move(*point)
                                kid.mouse.up()
                            else:
                                kid.locator('#activity button[name="answer"]').filter(has_text=item["answer"]).first.click()
                            expect(kid.locator(".answer-party")).to_be_visible()
                            expect(kid.get_by_text("Step 2 of " + str(len(LESSONS[key]["items"])), exact=True)).to_be_visible()
                    browser.close()

    def test_keyboard_word_number_and_discovery_lessons(self):
        parent = get_user_model().objects.get(username="reviewer")
        household = Client()
        household.force_login(parent)
        for size, width in (("desktop", 1200), ("phone", 375)):
            for theme in ("light", "dark"):
                self.variant = f"{size}-{theme}"
                child = Learner.objects.create(parent=parent, nickname="Rowan")
                keys = ("shift", "arrow-maze", "backspace", "left-right", "scissors", "rhymes", "syllables",
                        "magic-e", "sentence", "more", "twos", "measure", "coins", "clock", "sink-float", "living")
                rows = {name: assign_lesson(child, name + "-v1", 0) for name in keys}
                device = Client()
                device.force_login(parent)
                device.post(reverse("manage", args=[child.pk]), {"action": "play"})
                with self.subTest(size=size, theme=theme), sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
                    contexts = [browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme)
                                for _ in range(2)]
                    for ctx, session in zip(contexts, (household, device)):
                        ctx.add_cookies([{"name": "sessionid", "value": session.cookies["sessionid"].value,
                                          "url": self.live_server_url}])
                    contexts[1].add_init_script("""window.deviceVoiceCalls = 0;
                        Object.defineProperty(window, "speechSynthesis", {value: {
                          cancel() {}, speak() { window.deviceVoiceCalls++; }
                        }});""")
                    viewer, kid = [ctx.new_page() for ctx in contexts]
                    errors = []
                    for page in (viewer, kid):
                        page.on("pageerror", lambda error: errors.append(str(error)))
                    viewer.goto(self.live_server_url + reverse("coview"))
                    viewer.get_by_label("Show", exact=True).select_option(str(child.pk))
                    tile = viewer.locator(f'[data-child="{child.pk}"]')
                    for name, row in rows.items():
                        kid.goto(self.live_server_url + reverse("play", args=[row.pk]))
                        item = row.round_snapshot["items"][0]
                        board = kid.locator(".garden-tool")
                        if name == "shift":
                            kid.keyboard.press("f")
                            expect(kid.locator(".retry-note")).to_be_visible()
                            kid.keyboard.down("Shift")
                            expect(board.locator('[data-action="shift"]')).to_have_attribute("aria-pressed", "true")
                        elif name == "arrow-maze":
                            kid.keyboard.press("ArrowDown")
                            expect(board.locator("[data-maze] span").first).to_have_text("🐞")
                            for direction in ["ArrowRight", "ArrowRight", "ArrowDown", "ArrowDown", "ArrowRight"]:
                                kid.keyboard.press(direction)
                        elif name == "backspace":
                            kid.keyboard.press("Backspace")
                            expect(board.locator("output")).to_have_text(item["answer"])
                        elif name in ("rhymes", "syllables"):
                            kid.get_by_role("button", name="Hear directions").click()
                            kid.wait_for_function("document.querySelector('#directions-audio').currentTime > 0")
                            kid.get_by_role("button", name="Hear the word").click()
                            kid.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                            self.assertTrue(kid.locator("#directions-audio").evaluate("el => el.paused"))
                            path = kid.locator(".word-station audio").get_attribute("src")
                            self.assertTrue(path.endswith("/words/" + item["word"] + ".ogg"))
                            if name == "rhymes":
                                kid.route("**/phonics/words/*.ogg*", lambda route: route.abort())
                                kid.locator(".word-station audio").evaluate("audio => audio.src += '?offline-test'")
                                kid.get_by_role("button", name="Hear the word").click()
                                expect(kid.locator("#audio-status")).to_be_visible()
                                expect(kid.locator(".word-station details p")).to_be_visible()
                                self.assertEqual(kid.evaluate("window.deviceVoiceCalls"), 0)
                                self.capture(kid, "piper-word-offline")
                                kid.unroute("**/phonics/words/*.ogg*")
                                kid.get_by_role("button", name="Hear the word").click()
                                kid.wait_for_function("document.querySelector('.word-station audio').currentTime > 0")
                                expect(kid.locator("#audio-status")).to_be_hidden()
                            if name == "syllables":
                                pad = board.get_by_role("button", name="Tap the drum")
                                hit = board.locator("[data-drum-sound]")
                                hit.evaluate("""el => {
                                    window.drumHits = 0;
                                    el.addEventListener("playing", () => window.drumHits++);
                                }""")
                                pad.click()
                                kid.wait_for_function("window.drumHits === 1")
                                expect(board.locator("[data-count]")).to_have_text("1")
                                kid.wait_for_function("document.querySelector('[data-drum-sound]').ended")
                                pad.press("Space")
                                kid.wait_for_function("window.drumHits === 2")
                                expect(board.locator("[data-count]")).to_have_text("2")
                                expect(tile.locator("[data-count]")).to_have_text("2")
                                expect(tile.locator("[data-drum-sound]")).to_have_count(0)
                                board.get_by_role("button", name="Start over").click()
                                expect(board.locator("[data-count]")).to_have_text("0")
                                pad.press("Enter")
                                expect(board.locator("[data-count]")).to_have_text("1")
                        elif name == "magic-e":
                            expect(board.locator(".picture-choices")).to_be_hidden()
                            board.get_by_role("button", name="Add e").click()
                            expect(board.locator(".garden-sign")).to_have_text("cape")
                        elif name == "sentence":
                            for word in item["answer"].split():
                                board.get_by_role("button", name=word, exact=True).click()
                            expect(board.locator("output")).to_have_text(item["answer"])
                        elif name == "twos":
                            for button in board.locator("[data-pair]").all():
                                button.click()
                        elif name == "measure":
                            for _ in range(item["length"]):
                                board.get_by_role("button", name="Lay one acorn").click()
                        elif name == "coins":
                            board.locator('[data-coin="5"]').click()
                            board.locator('[data-coin="1"]').click()
                            expect(tile.locator(".coin-counter output")).to_have_text("5¢ + 1¢", timeout=10000)
                        elif name == "clock":
                            expect(board.locator(".lesson-clock text")).to_have_count(12)
                        kid.locator("article").screenshot(path=self.out / f"{self.variant}-practice-{name}.png")
                        self.assertFalse(kid.evaluate("document.documentElement.scrollWidth > innerWidth"))
                        if name == "shift":
                            kid.keyboard.press("F")
                            kid.keyboard.up("Shift")
                        elif name == "arrow-maze":
                            kid.keyboard.press("ArrowRight")
                        else:
                            kid.locator(f'#activity button[name="answer"][value="{item["answer"]}"]').click()
                        expect(kid.locator(".answer-party")).to_be_visible()
                    self.assertEqual(errors, [])
                    browser.close()
                self.assertEqual(child.assignment_set.filter(step=1).count(), len(keys))

    def test_themed_lessons(self):
        from pilot.themes import THEMES
        from pilot.practice import build_round
        parent = get_user_model().objects.get(username="reviewer")
        login = Client()
        login.force_login(parent)
        dot_round = next(n for n in range(1, 200) if build_round("lowercase-v1", n)["items"][0]["answer"] == "i")
        for size, width in (("desktop", 1200), ("phone", 375)):
            for theme in ("light", "dark"):
                child = Learner.objects.create(parent=parent, nickname="Juniper")
                row = assign_lesson(child, "berry-basket-v1", 0)
                device = Client()
                device.force_login(parent)
                device.post(reverse("manage", args=[child.pk]), {"action":"play"})
                self.variant = f"{size}-{theme}"
                with self.subTest(size=size, theme=theme), sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
                    contexts = [browser.new_context(viewport={"width":width,"height":820},color_scheme=theme) for _ in range(2)]
                    for ctx, session in zip(contexts, (login, device)):
                        ctx.add_cookies([{"name":"sessionid","value":session.cookies["sessionid"].value,"url":self.live_server_url}])
                    page, kid = [ctx.new_page() for ctx in contexts]
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk, "ten-v1", 0]))
                    garden = page.locator(".question-landscape")
                    expect(garden).to_have_attribute("data-world", "garden")
                    garden.screenshot(path=self.out / f"{self.variant}-scenery-garden.png")
                    for slug in ["construction","ocean","trains","woodland","bakery","dinosaurs","farm","space"]:
                        page.goto(self.live_server_url)
                        panel = page.locator("article").filter(has=page.get_by_role("link",name="Browse lesson library")).filter(
                            has=page.locator(f'form[action="/children/{child.pk}/"]'))
                        panel.locator(".learner-toggle").click()
                        panel.get_by_role("combobox").select_option(slug)
                        panel.get_by_role("button", name="Save lesson theme").click()
                        expect(panel.get_by_role("combobox")).to_have_value(slug)
                        panel.get_by_role("link", name="Browse lesson library").click()
                        expect(page.locator("main")).to_contain_text(THEMES[slug]["label"])
                        page.locator('[data-lesson="ten-v1"]').get_by_role("link",name="Preview lesson").click()
                        expect(page.locator(".lesson-setting")).to_contain_text(THEMES[slug]["label"])
                        expect(page.locator(".themed-cell")).to_have_count(5)
                        expect(garden).to_have_attribute("data-world", slug)
                        expect(garden.locator("use")).to_have_attribute("href", re.compile(f"#{slug}$"))
                        page.wait_for_function("document.querySelector('.question-scenery use').getBBox().width > 0")
                        garden.screenshot(path=self.out / f"{self.variant}-scenery-{slug}.png")
                        page.locator("article").filter(has=page.locator("#activity")).screenshot(path=self.out / f"{self.variant}-world-{slug}.png")
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                    page.goto(self.live_server_url)
                    panel.locator(".learner-toggle").click()
                    panel.get_by_text("Skill placement and progress", exact=True).click()
                    panel.get_by_role("button", name="Keyboard check-in", exact=True).click()
                    expect(panel.locator("[data-current-queue]")).to_contain_text("Keyboard check-in")
                    expect(panel.locator("[data-available-checkins]")).not_to_contain_text("Keyboard check-in")
                    expect(panel.locator("[data-placement-panel]")).to_have_attribute("open", "")
                    expect(panel.locator("[data-placement-panel] > summary")).to_be_focused()
                    page.goto(self.live_server_url + reverse("coview"))
                    page.get_by_label("Show", exact=True).select_option(str(child.pk))
                    tile = page.locator(f'[data-child="{child.pk}"]')
                    kid.goto(self.live_server_url + reverse("play", args=[row.pk]))
                    kid.get_by_role("button",name="Add one moon rock").click()
                    expect(tile.locator("[data-basket]")).to_have_text("🪨")
                    expect(tile.locator(".lesson-setting")).to_contain_text("Outer Space & Rockets")
                    for surface in (kid, tile):
                        expect(surface.locator(".question-scenery use")).to_have_attribute("href", re.compile("#space$"))
                    kid.locator("article.learner-step").screenshot(path=self.out / f"{self.variant}-scenery-in-play.png")
                    kid.get_by_role("button",name="Add one moon rock").click()
                    kid.get_by_role("button",name="Check cargo bay").click()
                    expect(kid.locator(".answer-party")).to_be_visible()
                    page.goto(self.live_server_url + reverse("preview", args=[child.pk,"lowercase-v1",0]) + f"?v={dot_round}")
                    guide = page.locator("#guide")
                    guide.scroll_into_view_if_needed()
                    points = guide.evaluate("""p => Array.from({length:19}, (_,i) => {
                      const at = p.getPointAtLength(i*p.getTotalLength()/18).matrixTransform(p.getScreenCTM());
                      return [at.x, at.y]; })""")
                    page.mouse.move(*points[0]); page.mouse.down()
                    for point in points[1:]:
                        page.mouse.move(*point)
                    page.mouse.up()
                    expect(page.locator("[data-stroke-help]")).to_contain_text("Stroke 2")
                    page.locator("#dot").click()
                    expect(page.locator(".answer-party")).to_be_visible()
                    browser.close()

    def test_fit_filters_and_tier_climb(self):
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        for size, width in (("desktop", 1200), ("phone", 375)):
            for theme in ("light", "dark"):
                self.variant = f"{size}-{theme}"
                child = Learner.objects.create(parent=parent, nickname="Ivy")
                first = child.assignment_set.create(lesson="count1-v1", completed=timezone.now())
                first.samples.create(step=0, strand="Number sense", level=1, score=100)
                device = Client()
                device.force_login(parent)
                device.post(reverse("manage", args=[child.pk]), {"action": "play"})
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
                    with self.subTest(size=size, theme=theme), browser.new_context(
                        viewport={"width": width, "height": 820}, color_scheme=theme
                    ) as family_ctx, browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme) as kid_ctx:
                        for ctx, session in ((family_ctx, family), (kid_ctx, device)):
                            ctx.add_cookies([{"name": "sessionid", "value": session.cookies["sessionid"].value,
                                              "url": self.live_server_url}])
                        page, kid = family_ctx.new_page(), kid_ctx.new_page()
                        page.goto(self.live_server_url + reverse("library", args=[child.pk]))
                        page.get_by_label("Lesson tier").select_option("4")
                        page.get_by_label("Fit for Ivy").select_option("Above level")
                        page.get_by_role("button", name="Filter lessons").click()
                        page.get_by_text("How lesson tiers and fit work").click()
                        expect(page.locator('[data-lesson="ten-v1"]')).to_be_visible()
                        self.capture(page, "tier-filters")
                        preview = page.get_by_role("link", name="Preview the tier celebration")
                        preview_url = self.live_server_url + reverse("tier_preview")
                        expect(preview).to_have_attribute("href", reverse("tier_preview"))
                        # Use the direct link as a signed-out visitor. Replaying recreates the real animation.
                        with browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme,
                                                 reduced_motion="reduce" if theme == "dark" else "no-preference") as guest:
                            demo = guest.new_page()
                            demo.goto(preview_url)
                            note = demo.locator('.tier-preview [data-variant="beanstalk"]')
                            expect(note).to_contain_text("Up to tier 3!")
                            first_note = note.element_handle()
                            demo.get_by_role("button", name="Replay the climb").click()
                            self.assertFalse(first_note.evaluate("el => el.isConnected"))
                            self.assertEqual(note.locator(".climber").evaluate("el => el.getAnimations().length"), int(theme == "light"))
                            self.capture(demo, "tier-preview")
                        page.get_by_role("button", name="Add all (", exact=False).click()
                        expect(page.locator("[data-empty]")).to_be_visible()
                        kid.goto(self.live_server_url)
                        kid.locator("article").filter(has=kid.get_by_role("heading", name="Make ten", exact=True)).get_by_role("link").click()
                        page.goto(self.live_server_url + reverse("coview"))
                        page.get_by_label("Show", exact=True).select_option(str(child.pk))
                        tile = page.locator(f'[data-child="{child.pk}"]')
                        expect(tile.locator("h3")).to_be_visible(timeout=10000)
                        reduced = theme == "dark"
                        if reduced:
                            kid.emulate_media(reduced_motion="reduce")
                        kid.locator('#activity button[value="' + LESSONS["ten-v1"]["items"][0]["answer"] + '"]').click()
                        climb = kid.locator('[data-variant="beanstalk"]')
                        expect(climb).to_contain_text("Up to tier 4!")
                        self.assertEqual(bool(climb.locator(".climber").evaluate("el => el.getAnimations().length")), not reduced)
                        kid.screenshot(path=self.out / f"{self.variant}-tier-climb.png")
                        expect(tile.locator('[data-variant="beanstalk"]')).to_contain_text("Number sense")
                        expect(kid.get_by_text("Step 2 of 3", exact=True)).to_be_visible()
                    browser.close()

    def test_family_co_view(self):
        from django.core.cache import caches
        fern = Learner.objects.get(pk=self.child_id)
        ash = Learner.objects.create(parent=fern.parent, nickname="Ash")
        art = assign_lesson(fern, "color-v1")
        seen_variants = set()
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
                        for index, cookie in enumerate(cookies):
                            context = browser.new_context(viewport={"width": width, "height": 820}, color_scheme=theme)
                            relay_only = size == "phone" and theme == "light"
                            if (index == 1 and size == "phone") or (index == 2 and relay_only):
                                context.add_init_script("window.RTCPeerConnection = undefined")
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
                            expect(ash_tile.locator(".live-status")).to_have_text(
                                "Live · Server relay" if relay_only else "Live · Direct", timeout=15000)
                            expect(fern_tile.locator(".live-status")).to_have_text(
                                "Live · Server relay" if size == "phone" else "Live · Direct", timeout=15000)
                            self.capture(viewer, "coview-together")
                            picker.select_option(str(ash.pk))
                            expect(fern_tile).to_be_hidden()
                            typist.locator('input[name="answer"]').fill("fern bed")
                            expect(ash_tile.locator("output")).to_have_text("fern bed")
                            self.capture(viewer, "coview-single")
                            if size == "desktop" and theme == "light":
                                from urllib.parse import parse_qs
                                def is_metadata(request):
                                    fields = parse_qs(request.post_data or "")
                                    return "/co-view/share/" in request.url and fields.get("metadata") == ["1"] and "typed" not in fields
                                with typist.expect_request(is_metadata, timeout=8000):
                                    pass
                                posts = []
                                typist.on("request", lambda req: posts.append(req.post_data) if "/co-view/share/" in req.url else None)
                                with typist.expect_request(is_metadata, timeout=8000):
                                    typist.locator('input[name="answer"]').fill("direct only")
                                    expect(ash_tile.locator("output")).to_have_text("direct only")
                                self.assertTrue(posts)
                                self.assertFalse(any("typed" in parse_qs(body or "") for body in posts))
                                ash_tile.evaluate("tile => tile.peer.close()")
                                typist.locator('input[name="answer"]').fill("relay works")
                                expect(ash_tile.locator(".live-status")).to_have_text("Live · Server relay")
                                expect(ash_tile.locator("output")).to_have_text("relay works", timeout=8000)
                                self.capture(viewer, "coview-relay-recovery")
                            check_direct = not relay_only and (size, theme) != ("desktop", "light")
                            if check_direct:
                                peer_id = ash_tile.evaluate("tile => tile.peer.id")
                                ash_tile.evaluate("""tile => {
                                    tile.statuses = [];
                                    new MutationObserver(() => tile.statuses.push(tile.querySelector(".live-status").textContent))
                                      .observe(tile.querySelector(".live-status"), {childList: true, subtree: true});
                                }""")

                            if relay_only:
                                # The entire child celebration happens between viewer polls.
                                viewer.evaluate("""() => {
                                    const fetchNow = window.fetch;
                                    const gate = new Promise(resolve => window.resumeWatch = resolve);
                                    window.fetch = async (url, options) => {
                                        if (String(url).includes("/co-view/watch/")) await gate;
                                        return fetchNow(url, options);
                                    };
                                }""")
                            prompt = ash_tile.locator(".live-scene h3")
                            prompt_text = prompt.inner_text()
                            question_node = prompt.element_handle()
                            typist.locator('input[name="answer"]').fill("red pot")
                            typist.get_by_role("button", name="Check sign").click()
                            child_party = typist.locator(".answer-party")
                            expect(child_party).to_be_visible()
                            variant = child_party.get_attribute("data-variant")
                            seen_variants.add(variant)
                            if relay_only:
                                expect(typist.get_by_text("Step 2 of 3", exact=True)).to_be_visible()
                                viewer.evaluate("window.resumeWatch()")
                            party = ash_tile.locator(".answer-party")
                            expect(party).to_have_attribute("data-variant", variant)
                            expect(prompt).to_have_text(prompt_text)
                            self.assertTrue(party.evaluate("""el => el.getBoundingClientRect().top >=
                                el.closest(".live-scene").querySelector("h3").getBoundingClientRect().bottom"""))
                            self.assertTrue(question_node.evaluate("(el) => el.isConnected"))
                            expect(ash_tile.locator("output")).to_have_text("red pot")
                            # Sample real painted movement before pausing for the screenshot.
                            self.assertTrue(party.evaluate("""async el => {
                                const particle = el.querySelector("i");
                                const before = particle.getBoundingClientRect();
                                await new Promise(resolve => setTimeout(resolve, 140));
                                const after = particle.getBoundingClientRect();
                                return el.isConnected && (after.x !== before.x || after.y !== before.y);
                            }"""))
                            # Capture the actual animation mid-flight on the mirror.
                            party.evaluate("""el => el.getAnimations({subtree:true}).forEach(anim => {
                                anim.pause(); anim.currentTime = 520;
                            })""")
                            ash_tile.screenshot(path=self.out / f"{self.variant}-mirror-success.png")
                            expect(ash_tile).to_contain_text("Answered red pot")
                            expect(ash_tile).to_contain_text("Step 2 of 3")
                            if check_direct:
                                typist.get_by_role("button", name="Skip this question").click()
                                expect(ash_tile).to_contain_text("Step 3 of 3")
                                typist.locator('input[name="answer"]').fill(typing.round_snapshot["items"][2]["answer"])
                                typist.get_by_role("button", name="Check sign").click()
                                expect(ash_tile.locator(".answer-party")).to_be_visible()
                                expect(ash_tile).to_contain_text("My lessons")
                                self.assertEqual(ash_tile.evaluate("tile => tile.peer.id"), peer_id, ash_tile.evaluate("tile => tile.statuses"))
                                self.assertEqual(ash_tile.evaluate("tile => tile.statuses.filter(s => s !== 'Live · Direct')"), [])
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
        self.assertEqual(seen_variants, {"popper", "bloom", "stars", "butterfly"})

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
        password = page.get_by_label(re.compile(r"^Password:?$"))
        expect(password).to_have_attribute("type", "password")
        password.fill("gardenexample")
        password.evaluate("el => el.setSelectionRange(6, 6)")
        page.get_by_role("button", name="Show password").click()
        expect(password).to_have_attribute("type", "text")
        expect(password).to_be_focused()
        password.press("Space")
        expect(password).to_have_value("garden example")
        self.capture(page, "password-visible")
        hide = page.get_by_role("button", name="Hide password")
        hide.focus()
        hide.press("Enter")
        expect(password).to_have_attribute("type", "password")
        expect(page.get_by_role("button",name="Show password")).to_be_focused()
        expect(password).to_have_value("garden example")
        page.locator("#id_username").fill("reviewer")
        page.locator("#id_password").fill("garden-qa-only")
        page.locator("#id_password").press("Enter")
        page.wait_for_url(self.live_server_url + "/")
        self.capture(page, "parent")

        page.get_by_role("link", name="Browse lesson library").click()
        self.capture(page, "library")
        card = page.locator("article").filter(has=page.get_by_role("heading", name="Count the seeds", exact=True))
        expect(card).to_contain_text("3 steps")
        card.get_by_role("link", name="Preview lesson").click()
        page.get_by_role("navigation", name="Preview steps").get_by_role("link", name="3").click()
        expect(page.get_by_text("Step 3 of 3", exact=True)).to_be_visible()
        self.capture(page, "counting-preview")
        page.emulate_media(reduced_motion="reduce")
        page.locator('#activity button[value="3"]').click()
        party = page.locator(".answer-party")
        expect(party).to_be_visible()
        self.assertEqual(party.evaluate("(el) => el.getAnimations({subtree: true}).length"), 0)
        expect(page.get_by_role("heading", name="Preview complete")).to_be_visible()
        page.emulate_media(reduced_motion="no-preference")
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
        page.locator(".learner-toggle").first.click()
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
        expect(party).to_be_visible()
        # Freeze a representative instant for the screenshot only. Navigation uses wall time.
        party.evaluate("""el => el.getAnimations({subtree:true}).forEach(animation => {
            animation.pause(); animation.currentTime = 550;
        })""")
        page.screenshot(path=self.out / f"{self.variant}-correct.png")
        page.keyboard.press("a")
        expect(page.get_by_text("Step 2 of 5", exact=True)).to_be_visible()
        page.get_by_role("button", name="Skip this question").click()
        page.get_by_role("button", name="Skip this question").click()
        expect(page.get_by_text("Step 4 of 5", exact=True)).to_be_visible()
        target4, target5 = [i["answer"] for i in LESSONS["keys-v2"]["items"][3:]]
        page.keyboard.press("z" if target4 != "Z" else "x")
        retry = page.get_by_text("Try again", exact=True)
        expect(retry).to_be_visible()
        self.capture(page, "try-again")
        page.locator("[data-screen-keyboard] summary").click()
        page.get_by_role("button", name=target4, exact=True).click()
        expect(page.get_by_text("Step 5 of 5", exact=True)).to_be_visible()
        self.capture(page, "five-key-finish")
        page.keyboard.press(target5.lower())
        expect(page).to_have_url(self.live_server_url + "/")
        page.get_by_role("link", name="Parent sign in").click()
        page.locator("#id_username").fill("reviewer")
        page.locator("#id_password").fill("garden-qa-only")
        page.locator("#id_password").press("Enter")
        page.locator(".learner-toggle").first.click()
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

    def test_focus_configuration_week_and_evidence(self):
        from pilot.assignments import assign_lesson
        parent = get_user_model().objects.get(username="reviewer")
        family = Client()
        family.force_login(parent)
        cases = []
        for width in (375,1200):
            for theme in ("light","dark"):
                child = Learner.objects.create(parent=parent,nickname="Fern")
                row = assign_lesson(child,"keys-v2",0,purpose="placement")
                row.samples.create(step=0,strand="Keyboard use",level=1,score=100,
                                   direct={"objective":"keys","facets":{"letters":["S"]}})
                cases.append((width,theme,child.pk))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width,theme,child_id in cases:
                self.variant = f"focus-{width}-{theme}"
                with browser.new_context(viewport={"width":width,"height":820},color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                    page = ctx.new_page()
                    page.goto(self.live_server_url+reverse("focus",args=[child_id]))
                    self.capture(page,"empty")
                    page.get_by_label("Focus name",exact=True).fill("Keyboard practice")
                    page.get_by_role("button",name="Save focus").click()
                    expect(page.get_by_text("Choose a subject, target or interest",exact=False)).to_be_visible()
                    page.get_by_label("Letters",exact=True).fill("M S")
                    page.get_by_role("button",name="Save focus").click()
                    expect(page.get_by_role("heading",name="Keyboard practice")).to_be_visible()
                    self.capture(page,"saved")
                    page.get_by_role("link",name="Weekly plan").click()
                    self.capture(page,"week")
                    page.goto(self.live_server_url+reverse("skill_report",args=[child_id]))
                    page.get_by_label("Evidence from").select_option("placement")
                    page.get_by_role("button",name="Show evidence").click()
                    page.locator("summary").filter(has_text="Keyboard and mouse").click()
                    page.locator(".focus-branch > summary").filter(has_text="Keyboard").click()
                    expect(page.get_by_text("Letter · S")).to_be_visible()
                    self.capture(page,"skills")
                    page.get_by_role("link",name="Find a letter key",exact=True).click()
                    expect(page.get_by_role("link",name="Check Z",exact=True)).to_be_visible()
                    self.capture(page,"targets")
                    page.get_by_role("link",name="Check Z",exact=True).click()
                    expect(page.locator("[data-question-start]")).to_have_text("Step 1 of 1")
            browser.close()

    def test_cross_lesson_focus_examples(self):
        parent = get_user_model().objects.get(username="reviewer")
        child = Learner.objects.create(parent=parent, nickname="Fern")
        child.focuses.create(name="Five, M and S",
                             config={"letters":["M","S"], "numbers":["5"], "context":85, "mode":"only"})
        older = Learner.objects.create(parent=parent, nickname="Sage")
        older.focuses.create(name="Eight", config={"numbers":["8"], "context":65, "mode":"only"})
        family = Client()
        family.force_login(parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375,1200):
                for theme in ("light","dark"):
                    self.variant = f"focus-examples-{width}-{theme}"
                    with browser.new_context(viewport={"width":width,"height":820},color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,
                                          "url":self.live_server_url}])
                        page = ctx.new_page()
                        for group in ("berry-basket","more","harvest","animal-lookout"):
                            page.goto(self.live_server_url+reverse("preview",args=[child.pk,group+"-v1",0])+"?v=2")
                            if group == "berry-basket":
                                page.locator("#add-berry").click()
                                expect(page.locator("#check-basket")).to_have_attribute("value","1")
                            elif group == "more":
                                expect(page.get_by_role("button",name=re.compile("pile with 5 "))).to_be_visible()
                            elif group == "harvest":
                                expect(page.locator("[data-carrots]")).to_have_attribute("data-carrots","10")
                            else:
                                expect(page.locator("#prompt")).to_have_text(re.compile(r"find the [ms]", re.I))
                            self.capture(page,group)
                        page.goto(self.live_server_url+reverse("preview",args=[older.pk,"more-v1",0])+"?v=2")
                        pile = page.get_by_role("button",name=re.compile("pile with 8 "))
                        expect(pile.locator(".acorn-pile i")).to_have_count(8)
                        self.capture(page,"larger-piles")
                        page.goto(self.live_server_url+reverse("preview",args=[older.pk,"berry-basket-v1",0])+"?v=2")
                        for _ in range(8):
                            page.locator("#add-berry").click()
                        expect(page.locator("#check-basket")).to_have_attribute("value","8")
                        self.capture(page,"larger-basket")
            browser.close()

    def test_collapsed_cards_and_installed_gardens(self):
        from pilot.assignments import assign_lesson
        parent = get_user_model().objects.get(username="reviewer")
        children = [Learner.objects.create(parent=parent,nickname=name) for name in ("Linden","Hazel")]
        for child in children:
            assign_lesson(child,"keys-v2",0)
        family = Client()
        family.force_login(parent)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375,1200):
                for theme in ("light","dark"):
                    self.variant = f"learner-cards-{width}-{theme}"
                    with browser.new_context(viewport={"width":width,"height":820},color_scheme=theme) as ctx:
                        ctx.add_cookies([{"name":"sessionid","value":family.cookies["sessionid"].value,"url":self.live_server_url}])
                        parent_page = ctx.new_page()
                        parent_page.goto(self.live_server_url)
                        card = parent_page.locator(f'[data-learner="{children[0].pk}"]')
                        expect(card.locator(".family-card-body")).to_be_hidden()
                        self.capture(parent_page,"collapsed")
                        card.locator(".learner-toggle").click()
                        expect(card.get_by_text("Lesson queue",exact=True)).to_be_visible()
                        card.locator(".learner-toggle").click()
                        menu = card.get_by_label("Tools for Linden",exact=True).first
                        menu.click()
                        expect(card.get_by_role("link",name="Skill details")).to_be_visible()
                        self.capture(parent_page,"menu")
                        parent_page.keyboard.press("Escape")
                        expect(card.get_by_role("link",name="Skill details")).not_to_be_visible()
                        expect(menu).to_be_focused()
                        menu.click()
                        card.get_by_role("link",name="Learner devices").click()
                        self.capture(parent_page,"devices")
                        if (width,theme) != (375,"light"):
                            continue
                        launches = []
                        for child in children:
                            parent_page.goto(self.live_server_url+reverse("devices",args=[child.pk]))
                            parent_page.get_by_label("Device name").fill("Garden tablet")
                            parent_page.get_by_role("button",name="Create setup code").click()
                            setup = parent_page.get_by_role("status")
                            url = setup.get_by_role("link").get_attribute("href")
                            code = setup.locator(".device-code").inner_text()
                            tab = ctx.new_page()
                            tab.goto(url)
                            self.capture(tab,"connect")
                            tab.get_by_label("One-time setup code").fill(code)
                            tab.get_by_role("button",name="Connect this garden").click()
                            expect(tab.get_by_role("heading",name=child.nickname+"’s garden")).to_be_visible()
                            expect(tab.get_by_role("link",name="Admin dashboard")).to_have_count(0)
                            tab.get_by_role("link",name="Start lesson").click()
                            expect(tab).to_have_url(re.compile(re.escape(url)+"play/"))
                            tab.get_by_role("link",name="My lessons").click()
                            launches.append((url,tab))
                        for (url,tab),child in zip(launches,children):
                            tab.goto(url)
                            expect(tab.get_by_role("heading",name=child.nickname+"’s garden")).to_be_visible()
                        parent_page.get_by_role("button",name="Remove access",exact=False).click()
                        launches[-1][1].reload()
                        expect(launches[-1][1].get_by_text("This shortcut has expired",exact=False)).to_be_visible()
                        parent_page.goto(self.live_server_url)
                        expect(parent_page.get_by_role("heading",name="Family garden")).to_be_visible()
            browser.close()

    def test_device_key_survives_browser_restart(self):
        from tempfile import TemporaryDirectory
        from pilot.assignments import assign_lesson
        family = Client()
        child = Learner.objects.get(pk=self.child_id)
        assign_lesson(child,"keys-v2",0)
        family.force_login(child.parent)
        issued = family.post(reverse("devices",args=[child.pk]),{"label":"Dedicated tablet"},secure=True)
        code = issued.context["code"]
        url = self.live_server_url+f"/g/{child.devices.get().pk}/"
        with TemporaryDirectory(prefix="lg-browser-profile-") as profile, sync_playwright() as pw:
            opts = dict(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"),headless=True)
            ctx = pw.chromium.launch_persistent_context(profile,**opts)
            page = ctx.pages[0]
            page.goto(url)
            page.evaluate("navigator.serviceWorker.ready.then(() => true)")
            cdp = ctx.new_cdp_session(page)
            manifest = cdp.send("Page.getAppManifest")
            self.assertFalse(manifest["errors"])
            self.assertFalse(cdp.send("Page.getInstallabilityErrors")["installabilityErrors"])
            page.get_by_label("One-time setup code").fill(code)
            page.get_by_role("button",name="Connect this garden").click()
            expect(page.get_by_role("heading",name="Fern’s garden")).to_be_visible()
            ctx.clear_cookies()
            ctx.close()
            ctx = pw.chromium.launch_persistent_context(profile,**opts)
            page = ctx.pages[0]
            page.goto(url)
            expect(page.get_by_role("heading",name="Fern’s garden")).to_be_visible()
            page.get_by_role("link",name="Start lesson").click()
            expect(page.locator("#activity")).to_be_visible()
            ctx.close()

    def test_curriculum_gallery(self):
        """Refresh the public crops with UPDATE_GUIDE_SCREENSHOTS=1."""
        from pilot.public_guides import GALLERY
        family = Client()
        family.force_login(get_user_model().objects.get(username="reviewer"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            ctx = browser.new_context(viewport={"width": 660, "height": 940},
                                      color_scheme="light", reduced_motion="reduce")
            ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value,
                              "url": self.live_server_url}])
            page = ctx.new_page()
            for key, slug, _ in GALLERY:
                page.goto(self.live_server_url + reverse("preview", args=[self.child_id, key, 0]) + "?v=2")
                expect(page.get_by_role("button", name="Hear directions")).to_be_visible()
                filename = f"{slug}.png"
                target = Path("static/guides") / filename
                area = page.locator(".question-work-area")
                area.screenshot(path=self.out / filename, animations="disabled")
                if os.getenv("UPDATE_GUIDE_SCREENSHOTS") == "1":
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes((self.out / filename).read_bytes())
                self.assertTrue(target.is_file(), filename)
            browser.close()

    @override_settings(INVITE_REQUEST_RECIPIENTS=["review@example.org"])
    def test_public_family_guides(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width in (375, 1200):
                for theme in ("light", "dark"):
                    self.variant = f"guides-{width}-{theme}"
                    with browser.new_context(viewport={"width": width, "height": 840}, color_scheme=theme,
                                             reduced_motion="reduce") as ctx:
                        page = ctx.new_page()
                        page.goto(self.live_server_url)
                        self.capture(page, "welcome")
                        page.get_by_role("link", name="Curriculum", exact=True).click()
                        expect(page.locator(".lesson-gallery img")).to_have_count(3)
                        page.locator(".lesson-gallery img").evaluate_all(
                            "(images) => Promise.all(images.map(image => image.decode()))")
                        page.locator(".guide-topic summary").first.click()
                        self.capture(page, "curriculum")
                        page.get_by_role("link", name="How it works", exact=True).click()
                        page.get_by_role("link", name="Read progress", exact=True).click()
                        expect(page.locator("#progress h2")).to_be_in_viewport()
                        self.capture(page, "parent-guide")
                        page.get_by_role("navigation", name="Explore Little Garden").get_by_text("Request invite").click()
                        page.get_by_label("Parent or caregiver email").fill(f"guide-{width}-{theme}@example.org")
                        self.capture(page, "invite")
                        page.get_by_role("button", name="Request my invite").click()
                        expect(page.get_by_role("heading", name="Request received")).to_be_visible()
                        self.capture(page, "received")
                        share = page.get_by_role("navigation", name="Share Little Garden")
                        expect(share.get_by_role("link", name="Share on Facebook")).to_have_attribute("href", re.compile("littlegarden.academy"))
                        expect(share.locator(".share-icons a")).to_have_count(12)
                        for name in ("Instagram", "TikTok", "YouTube"):
                            share_link = share.get_by_role("link", name=f"Share on {name}", exact=True)
                            share_link.focus()
                            share_link.press("Enter")
                            panel = share.locator(".share-help:target")
                            expect(panel.get_by_role("link", name=f"Open {name}")).to_be_visible()
                            expect(panel.get_by_role("textbox")).to_have_value("https://littlegarden.academy/")
                            if name == "Instagram":
                                ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.live_server_url)
                                panel.get_by_role("button", name="Copy link").click()
                                expect(panel.get_by_role("status")).to_have_text("Link copied.")
                                self.assertEqual(page.evaluate("navigator.clipboard.readText()"),
                                                 "https://littlegarden.academy/")
                                self.capture(page, "social-sharing")
                            panel.get_by_role("link", name="Close").click()
                            expect(share.locator(".share-help:visible")).to_have_count(0)
            browser.close()

    @override_settings(INVITE_ONLY_SIGNUP=True, PUBLIC_HOST="testserver",
                       STRIPE_LIVE_ONE_TIME_LINK="https://donate.stripe.com/ExampleOnce",
                       STRIPE_LIVE_MONTHLY_LINK="https://buy.stripe.com/ExampleMonthly",
                       STRIPE_CUSTOMER_PORTAL_LINK="https://billing.stripe.com/p/login/ExamplePortal")
    def test_staff_requests_and_live_donation_handoff(self):
        from pilot.models import InviteRequest
        family = Client()
        family.force_login(get_user_model().objects.get(username="reviewer"))
        self.assertContains(family.get(reverse("invite_requests")), "No families have requested an invite yet.")
        cases = [(width, theme, InviteRequest.objects.create(email=f"{width}-{theme}@example.org",
                                                             notified_at=timezone.now()))
                 for width in (375, 1200) for theme in ("light", "dark")]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROME_PATH"))
            for width, theme, entry in cases:
                self.variant = f"guides-{width}-{theme}"
                with browser.new_context(viewport={"width": width, "height": 840}, color_scheme=theme) as ctx:
                    ctx.add_cookies([{"name": "sessionid", "value": family.cookies["sessionid"].value,
                                      "url": self.live_server_url}])
                    page = ctx.new_page()
                    page.goto(self.live_server_url + reverse("invite_requests"))
                    card = page.locator("article").filter(has_text=entry.email)
                    card.get_by_role("button", name="Send invitation").click()
                    expect(card).to_contain_text("Invited")
                    self.capture(page, "staff-invites")
                    page.route(re.compile(r"^https://(?:buy|donate|billing)\.stripe\.com/"),
                               lambda route: route.fulfill(status=200, body="QA checkout"))
                    page.goto(self.live_server_url + reverse("mission"))
                    for label, checkout in (("Give once", "https://donate.stripe.com/ExampleOnce"),
                                            ("Give monthly", "https://buy.stripe.com/ExampleMonthly"),
                                            ("Cancel monthly support", "https://billing.stripe.com/p/login/ExamplePortal")):
                        link = page.get_by_role("link", name=label)
                        link.scroll_into_view_if_needed()
                        self.capture(page, "live-donations")
                        link.click()
                        expect(page).to_have_url(checkout)
                        page.go_back()
            browser.close()
