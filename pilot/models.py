from django.conf import settings
from django.db import models


class Learner(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=40)


class Assignment(models.Model):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    lesson = models.CharField(max_length=80)
    variation = models.PositiveIntegerField(default=0)
    artwork = models.JSONField(null=True)
    round_snapshot = models.JSONField(null=True)
    position = models.IntegerField(default=0)
    step = models.PositiveIntegerField(default=0)
    retries = models.PositiveIntegerField(default=0)
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
    ms_per_key = models.PositiveIntegerField(null=True)
    measured = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "step"], name="one_skill_sample_per_step")]
