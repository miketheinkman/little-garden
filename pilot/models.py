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


class PracticeFocus(models.Model):
    learner = models.ForeignKey(Learner, related_name="focuses", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    config = models.JSONField(default=dict)
    paused = models.BooleanField(default=False)
    starts = models.DateField(null=True, blank=True)
    ends = models.DateField(null=True, blank=True)
    automatic = models.BooleanField(default=False)


class Purpose(models.TextChoices):
    PRACTICE = "practice", "Practice"
    PLACEMENT = "placement", "Initial placement"
    REVIEW = "review", "Skill review"


class LessonPlan(models.Model):
    focus_policy = models.JSONField(null=True, blank=True)
    follow_focus = models.BooleanField(default=True, db_default=True)
    class Repeat(models.TextChoices):
        ONCE = "once", "Just once"
        DAILY = "daily", "Every day"
        WEEKDAYS = "weekdays", "Monday through Friday"
        WEEKLY = "weekly", "Weekly on selected days"
        FOUR_WEEKS = "fourweeks", "Every four weeks"

    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=12, choices=Purpose.choices, default=Purpose.PRACTICE)
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
    purpose = models.CharField(max_length=12, choices=Purpose.choices, default=Purpose.PRACTICE)
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
    resolved = models.BooleanField(default=False)
    status_version = models.PositiveIntegerField(default=0)
    preview_settings = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created", "-pk"]
        permissions = [("review_lessons", "Access the lesson review dashboard")]


class FeedbackReply(models.Model):
    class Kind(models.TextChoices):
        REPLY = "reply", "Team reply"
        RESOLVE = "resolve", "Marked resolved"
        REOPEN = "reopen", "Reopened"

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.REPLY)
    feedback = models.ForeignKey(LessonFeedback, related_name="replies", on_delete=models.CASCADE)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    submission = models.UUIDField()
    text = models.CharField(max_length=2000, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created", "pk"]
        constraints = [models.UniqueConstraint(fields=["feedback", "submission"], name="unique_feedback_reply")]


class FeedbackEmailPreference(models.Model):
    parent = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)


class SkillSample(models.Model):
    direct = models.JSONField(default=dict, blank=True, db_default={})
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


class Observation(models.Model):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    assignment = models.ForeignKey(Assignment, null=True, blank=True, on_delete=models.SET_NULL)
    observed_on = models.DateField(db_index=True)
    text = models.CharField(max_length=2000)
    submission = models.UUIDField(default=uuid.uuid4)

    class Meta:
        ordering = ["-observed_on", "-pk"]
        constraints = [models.UniqueConstraint(fields=["learner", "submission"], name="unique_learner_observation")]


class QuestionAttempt(models.Model):
    direct = models.JSONField(default=dict, blank=True, db_default={})
    class Outcome(models.TextChoices):
        CORRECT = "correct", "Correct"
        INCORRECT = "incorrect", "Incorrect"
        SKIPPED = "skipped", "Skipped"
        COMPLETED = "completed", "Completed activity"
        RETRY = "retry", "Tried activity again"

    assignment = models.ForeignKey(Assignment, related_name="question_attempts", on_delete=models.CASCADE)
    step = models.PositiveIntegerField()
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    submission = models.UUIDField(null=True)
    prompt = models.CharField(max_length=600)
    expected = models.CharField(max_length=300, blank=True)
    response = models.CharField(max_length=300, blank=True)
    score = models.PositiveSmallIntegerField(null=True)
    ms_per_key = models.PositiveIntegerField(null=True)
    help_used = models.PositiveSmallIntegerField(default=0)
    advanced = models.BooleanField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assignment_id", "step", "pk"]
        constraints = [models.UniqueConstraint(fields=["assignment", "submission"], name="unique_question_submission")]


class ParentInvitation(models.Model):
    email = models.EmailField(unique=True)
    code_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)

    @classmethod
    def available(cls):
        return cls.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now())


class LearnerDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE, related_name="devices")
    label = models.CharField(max_length=60)
    code_digest = models.CharField(max_length=64, blank=True)
    expires = models.DateTimeField()
    certificate = models.BinaryField(default=bytes)
    generation = models.PositiveBigIntegerField(default=0)
    last_used = models.DateTimeField(null=True)


class InviteRequest(models.Model):
    email = models.EmailField(unique=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    invited_at = models.DateTimeField(null=True, blank=True)
