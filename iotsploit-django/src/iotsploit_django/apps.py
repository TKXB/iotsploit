from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)


class IoTSploitDjangoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iotsploit_django"

    def ready(self):
        from django.conf import settings

        logger.info("IoTSploit runtime mode: %s", settings.IOTSPLOIT_RUNTIME)
        # Observation tables live in their own SQLAlchemy metadata, so nothing
        # else creates them. Imported here rather than at module scope because
        # this runs before the Django app registry is populated.
        from iotsploit_django.adapters.django.observation_models import initialize_observation_schema

        initialize_observation_schema()

        # Register protocol facets before any target is hydrated, or stored
        # facets load as RawFacet and typed access silently returns nothing.
        # A facet ships with the code that consumes it, so they come from
        # wherever that code lives -- someip from iotsploit-protocols, the
        # others still from tools/ until their clients move there too.
        from iotsploit_django.tools import can_facet, doip_facet  # noqa: F401
        from iotsploit_protocols.someip import facet as someip_facet  # noqa: F401

        # `iotsploit_django.models` is deliberately framework-agnostic, so
        # Django's automatic <app>.models import registers nothing. ORM models
        # that need migrations are imported here instead.
        from iotsploit_django.adapters.django.interaction import models as interaction_models  # noqa: F401
