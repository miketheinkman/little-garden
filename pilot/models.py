from django.conf import settings
from django.db import models


class Learner(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=40)


class Assignment(models.Model):
    learner = models.ForeignKey(Learner, on_delete=models.CASCADE)
    lesson = models.CharField(max_length=80)
    position = models.IntegerField(default=0)
    step = models.PositiveIntegerField(default=0)
    retries = models.PositiveIntegerField(default=0)
    completed = models.DateTimeField(null=True)

    class Meta:
        ordering = ["position", "id"]
