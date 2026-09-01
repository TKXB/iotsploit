from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iotsploit_django", "0002_pluginexecution_inputrequest_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuzzingcampaign",
            name="runtime_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Runtime counters and worker metadata for this campaign",
            ),
        ),
        migrations.AlterField(
            model_name="fuzzingcampaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("idle", "Idle"),
                    ("starting", "Starting"),
                    ("running", "Running"),
                    ("paused", "Paused"),
                    ("stopped", "Stopped"),
                    ("reset", "Reset"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="idle",
                help_text="Campaign status",
                max_length=20,
            ),
        ),
    ]
