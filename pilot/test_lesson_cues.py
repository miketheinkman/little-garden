from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Learner
from .practice import LESSONS
from .templatetags.lesson_cues import ACTION_ICONS
from .views import assign_lesson


class LearnerAudioTests(TestCase):
    def test_catalog_including_saved_versions_has_question_art(self):
        for key in LESSONS:
            self.assertIn(key.rsplit("-v", 1)[0], ACTION_ICONS)

    def test_audio_setting_is_per_child_parent_owned_and_child_player_only(self):
        parent = get_user_model().objects.create_user("parent")
        child = Learner.objects.create(parent=parent, nickname="Fern")
        sibling = Learner.objects.create(parent=parent, nickname="Kit")
        other = Learner.objects.create(parent=get_user_model().objects.create_user("other"), nickname="Pip")
        manage = reverse("manage", args=[child.pk])
        row = assign_lesson(child, "sounds-v1")
        self.client.force_login(parent)
        self.assertEqual(self.client.post(reverse("manage", args=[other.pk]), {"action":"lesson-audio","autoplay_directions":"on"}).status_code, 404)
        self.assertFalse(child.autoplay_directions)
        self.client.post(manage, {"action":"lesson-audio","autoplay_directions":"on"})
        child.refresh_from_db()
        sibling.refresh_from_db()
        self.assertTrue(child.autoplay_directions)
        self.assertFalse(sibling.autoplay_directions)
        preview = self.client.get(reverse("preview", args=[child.pk, row.lesson, 0]))
        self.assertNotContains(preview, "data-autoplay-directions")
        self.client.post(manage, {"action":"play"})
        self.assertContains(self.client.get(reverse("play",args=[row.pk])), "data-autoplay-directions")
        self.client.force_login(parent)
        self.client.post(manage, {"action":"lesson-audio"})
        self.client.post(manage, {"action":"play"})
        self.assertNotContains(self.client.get(reverse("play",args=[row.pk])), "data-autoplay-directions")
