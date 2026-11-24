import re
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


FONT_CHOICES = (("default", "Garden default"), ("sans", "Simple sans serif"), ("serif", "Book serif"),
                ("mono", "Evenly spaced"))


class Learner(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=40)
    autoplay_directions = models.BooleanField(default=False)
    lesson_theme = models.CharField(max_length=20, default="garden")

    accent = models.CharField(max_length=7, blank=True, default="")
    font = models.CharField(max_length=12, choices=FONT_CHOICES, default="default")

    @property
    def appearance(self):
        accent = self.accent if re.fullmatch(r"#[0-9a-fA-F]{6}", self.accent) else ""
        ink = ""
        if accent:
            rgb = [int(accent[i:i+2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
            luminance = sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
            ink = "#000000" if luminance > .179 else "#ffffff"
        return {"accent": accent, "ink": ink, "font": self.font}


class LessonPlan(models.Model):
    class Repeat(models.TextChoices):
        ONCE = "once", "Just once"
        DAILY = "daily", "Every day"
        WEEKDAYS = "weekdays", "Monday through Friday"
        WEEKLY = "weekly", "Weekly on selected days"

    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    lesson = models.CharField(max_length=80)
    next_on = models.DateField(null=True, db_index=True)
    repeat = models.CharField(max_length=10, choices=Repeat.choices)
    weekdays = models.CharField(max_length=7, blank=True)
    ends_on = models.DateField(null=True)
    first_variation = models.PositiveIntegerField(null=True)
    letters = models.CharField(max_length=26, blank=True)
    submission = models.UUIDField(default=uuid.uuid4)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("learner", "submission"), name="unique_learner_plan_submission")]


class Assignment(models.Model):
    plan = models.ForeignKey(LessonPlan, null=True, on_delete=models.SET_NULL)
    scheduled_for = models.DateField(null=True)
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    lesson = models.CharField(max_length=80)
    variation = models.PositiveIntegerField(default=0)
    artwork = models.JSONField(null=True)
    round_snapshot = models.JSONField(null=True)
    position = models.IntegerField(default=0)
    step = models.PositiveIntegerField(default=0)
    puzzle_help = models.PositiveSmallIntegerField(default=0)
    retries = models.PositiveIntegerField(default=0)
    assigned_at = models.DateTimeField(default=timezone.now, null=True, editable=False)
    completed = models.DateTimeField(null=True)
    removed_at = models.DateTimeField(null=True)
    skipped = models.PositiveIntegerField(default=0)

    @property
    def answered(self):
        return self.step - self.skipped

    class Meta:
        ordering = ["position", "id"]


class LessonFeedback(models.Model):
    class Kind(models.TextChoices):
        WORKED = "worked", "What worked"
        CONFUSING = "confusing", "What was confusing"
        CHANGE = "change", "What I’d change"

    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lesson = models.CharField(max_length=80)
    variation = models.PositiveIntegerField(default=0)
    step = models.PositiveIntegerField(null=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    note = models.CharField(max_length=1500, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created", "-pk"]
        permissions = [("review_lessons", "Access the lesson review dashboard")]


class FeedbackReply(models.Model):
    feedback = models.ForeignKey(LessonFeedback, related_name="replies", on_delete=models.CASCADE)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    submission = models.UUIDField()
    text = models.CharField(max_length=2000)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created", "pk"]
        constraints = [models.UniqueConstraint(fields=["feedback", "submission"], name="unique_feedback_reply")]


class FeedbackEmailPreference(models.Model):
    parent = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)


class SkillSample(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="samples")
    step = models.PositiveIntegerField()
    strand = models.CharField(max_length=60)
    level = models.PositiveSmallIntegerField()
    score = models.PositiveSmallIntegerField()
    puzzle_help = models.PositiveSmallIntegerField(default=0)
    ms_per_key = models.PositiveIntegerField(null=True)
    peak_tier = models.PositiveSmallIntegerField(null=True)
    measured = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "step"], name="one_skill_sample_per_step")]
