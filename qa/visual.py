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
                        page.get_by_role("button", name="Add all (2)").click()
                        expect(page.locator("[data-empty]")).to_be_visible()
                        self.capture(page, "library-filter-queued")
                        kid.goto(self.live_server_url)
                        expect(kid.get_by_role("link", name="Start lesson")).to_have_count(6)
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
                                kid.wait_for_function("document.querySelector('audio').currentTime > 0")
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
                    contexts[1].add_init_script("""window.spoken = [];
                        Object.defineProperty(window, "speechSynthesis", {value: {
                          cancel() {}, speak(msg) {window.spoken.push([msg.text, msg.voice, msg.rate, msg.pitch])}
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
                            expect(board.get_by_role("button", name="Shift ⇧")).to_have_attribute("aria-pressed", "true")
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
                            kid.get_by_role("button", name="Hear the word").click()
                            directions, word = kid.evaluate("window.spoken")
                            self.assertEqual(directions[0], item["prompt"])
                            self.assertEqual(word[0], item["word"])
                            self.assertEqual(directions[1:], word[1:])
                            if name == "syllables":
                                board.get_by_role("button", name="Tap the drum").click()
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
                    for slug in ["construction","ocean","trains","woodland","bakery","dinosaurs","farm","space"]:
                        page.goto(self.live_server_url)
                        panel = page.locator("article").filter(has=page.get_by_role("link",name="Browse lesson library")).filter(
                            has=page.locator(f'form[action="/children/{child.pk}/"]'))
                        panel.get_by_role("combobox").select_option(slug)
                        panel.get_by_role("button", name="Save lesson theme").click()
                        expect(panel.get_by_role("combobox")).to_have_value(slug)
                        panel.get_by_role("link", name="Browse lesson library").click()
                        expect(page.locator("main")).to_contain_text(THEMES[slug]["label"])
                        page.locator('[data-lesson="ten-v1"]').get_by_role("link",name="Preview lesson").click()
                        expect(page.locator(".lesson-setting")).to_contain_text(THEMES[slug]["label"])
                        expect(page.locator(".themed-cell")).to_have_count(5)
                        page.locator("article").filter(has=page.locator("#activity")).screenshot(path=self.out / f"{self.variant}-world-{slug}.png")
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                    page.goto(self.live_server_url)
                    panel.get_by_text("Skill placement and progress", exact=True).click()
                    panel.get_by_role("button", name="Keyboard check-in", exact=True).click()
                    expect(panel.locator("[data-current-queue]")).to_contain_text("Keyboard check-in")
                    expect(panel.locator("[data-available-checkins]")).not_to_contain_text("Keyboard check-in")
                    expect(panel.locator("details").first).to_have_attribute("open", "")
                    page.goto(self.live_server_url + reverse("coview"))
                    page.get_by_label("Show", exact=True).select_option(str(child.pk))
                    tile = page.locator(f'[data-child="{child.pk}"]')
                    kid.goto(self.live_server_url + reverse("play", args=[row.pk]))
                    kid.get_by_role("button",name="Add one moon rock").click()
                    expect(tile.locator("[data-basket]")).to_have_text("🪨")
                    expect(tile.locator(".lesson-setting")).to_contain_text("Outer Space & Rockets")
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
        page.emulate_media(reduced_motion="reduce")
        page.locator('#activity button[value="2"]').click()
        party = page.locator(".answer-party")
        expect(party).to_have_text("🎉Correct!")
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
        page.keyboard.press("x")
        retry = page.get_by_text("Try again", exact=True)
        expect(retry).to_be_visible()
        self.capture(page, "try-again")
        page.get_by_role("button", name="S", exact=True).click()
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
