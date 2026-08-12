from django.apps import AppConfig


class IoTSploitDjangoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iotsploit_django"

    def ready(self):
        # Observation tables live in their own SQLAlchemy metadata, so nothing
        # else creates them. Imported here rather than at module scope because
        # this runs before the Django app registry is populated.
        from iotsploit_django.adapters.django.observation_models import initialize_observation_schema

        initialize_observation_schema()
