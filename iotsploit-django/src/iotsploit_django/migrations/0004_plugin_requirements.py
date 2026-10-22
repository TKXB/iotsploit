from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("iotsploit_django", "0003_fuzzingcampaign_runtime_state")]

    operations = [
        migrations.AddField(
            model_name="plugin",
            name="requirements",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
