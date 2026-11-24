"""Seed only the throwaway database created by qa/capacity.py."""
import json
import sys
from pathlib import Path

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from pilot.models import Assignment, Learner, SkillSample
from pilot.practice import build_round

root = Path.cwd()
if not (root / ".capacity-lab").is_file():
    raise RuntimeError("A fresh benchmark directory is required.")
if connection.vendor == "postgresql":
    if Path(settings.DATABASES["default"]["HOST"]) != root:
        raise RuntimeError("The PostgreSQL socket must belong to this fixture.")
    with connection.cursor() as cursor:
        cursor.execute("SHOW data_directory")
        if Path(cursor.fetchone()[0]) != root / "pgdata":
            raise RuntimeError("Wrong PostgreSQL data directory.")
elif settings.DATABASES["default"]["NAME"] != root / "db.sqlite3":
    raise RuntimeError("Wrong SQLite database.")
call_command("migrate", verbosity=0)
keys = ["keys-v2", "ten-v1", "number-keys-v2"]
rounds = {key: [build_round(key, v) for v in range(5)] for key in keys}
families = []
with transaction.atomic():
    for i in range(int(sys.argv[1])):
        parent = get_user_model().objects.create(username=f"fixture-{i}", password="!")
        child = Learner.objects.create(parent=parent, nickname="Seedling")
        child_session = SessionStore()
        child_session["child"] = child.pk
        child_session.save()
        viewer = SessionStore()
        viewer.update({"_auth_user_id": str(parent.pk), "_auth_user_backend": "django.contrib.auth.backends.ModelBackend",
                       "_auth_user_hash": parent.get_session_auth_hash()})
        viewer.save()
        past = Assignment.objects.bulk_create([
            Assignment(learner=child, lesson="keys-v2", step=5, completed=timezone.now()) for _ in range(10)])
        SkillSample.objects.bulk_create([SkillSample(assignment=row, step=j, strand="Keyboard use", level=1,
                                                    score=100, peak_tier=1) for row in past for j in range(5)])
        queue = []
        for j in range(5):
            key = keys[(i+j) % len(keys)]
            snapshot = rounds[key][(i+j) % 5]
            row = Assignment.objects.create(learner=child, lesson=key, round_snapshot=snapshot,
                                            variation=(i+j) % 5, position=j+1)
            queue.append([row.pk, [str(item["answer"]) for item in snapshot["items"]]])
        families.append([child.pk, child_session.session_key, viewer.session_key, queue])
(root / "families.json").write_text(json.dumps(families))
