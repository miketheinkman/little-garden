from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("pilot", "0012_learner_appearance")]

    operations = [
        # Older rows have no recorded queue date. Only new rows receive a timestamp.
        migrations.AddField("assignment", "assigned_at", models.DateTimeField(null=True, editable=False)),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.AlterField("assignment", "assigned_at", models.DateTimeField(default=timezone.now, null=True, editable=False)),
        ]),
    ]
