from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STRIPE_TEST_ONE_TIME_LINK="https://donate.stripe.com/test_Once",
                   STRIPE_TEST_MONTHLY_LINK="https://buy.stripe.com/test_Monthly")
class DonationTests(TestCase):
    def test_distinct_test_links_and_child_visibility(self):
        page = self.client.get(reverse("mission"))
        self.assertContains(page, 'href="https://donate.stripe.com/test_Once"')
        self.assertContains(page, 'href="https://buy.stripe.com/test_Monthly"')
        session = self.client.session
        session["child"] = 12
        session.save()
        self.assertNotContains(self.client.get(reverse("mission")), "stripe.com")

    def test_invalid_link_does_not_disable_other_frequency(self):
        for url in ("", "https://buy.stripe.com/liveLink", "https://example.org/test_Once"):
            with self.subTest(url=url), self.settings(STRIPE_TEST_ONE_TIME_LINK=url):
                page = self.client.get(reverse("mission"))
                self.assertNotContains(page, "Give once")
                self.assertContains(page, "Give monthly")

    def test_empty_and_duplicate_links_have_a_fallback(self):
        for url in ("", "https://buy.stripe.com/test_Duplicate"):
            with self.subTest(url=url), self.settings(STRIPE_TEST_ONE_TIME_LINK=url, STRIPE_TEST_MONTHLY_LINK=url):
                page = self.client.get(reverse("mission"))
                self.assertContains(page, "Online donations are coming soon")
                self.assertNotContains(page, "buy.stripe.com")

    def test_live_mode_uses_only_live_hosted_checkouts(self):
        with self.settings(STRIPE_LIVE_ONE_TIME_LINK="https://donate.stripe.com/abc01",
                           STRIPE_LIVE_MONTHLY_LINK="https://buy.stripe.com/test_Monthly"):
            page = self.client.get(reverse("mission"))
            self.assertContains(page, 'href="https://donate.stripe.com/abc01"')
            self.assertNotContains(page, "test_")
            self.assertNotContains(page, "Give monthly")
            self.assertNotContains(page, "sandbox")
        with self.settings(STRIPE_LIVE_MONTHLY_LINK="https://buy.stripe.com/abc02"):
            page = self.client.get(reverse("mission"))
            self.assertContains(page, "Give monthly")
            self.assertNotContains(page, "Give once")
