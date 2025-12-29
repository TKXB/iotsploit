"""Django model registry for the `iotsploit_django` app.

Stage-5.5 (aggressive): register migrated models under this app so migrations
can be generated and DB can be rebuilt.
"""

from __future__ import annotations

# Re-export models that were previously hosted under the legacy app.
# AI models / vehicles / etc.
from iotsploit_django.models.AIModel_Model import *  # noqa: F401,F403
from iotsploit_django.models.ClassifiedInfo_Model import *  # noqa: F401,F403
from iotsploit_django.models.DoIP_Diagnostic_Database_Model import *  # noqa: F401,F403
from iotsploit_django.models.PassCondition_Model import *  # noqa: F401,F403
from iotsploit_django.models.Vehicle_Model import *  # noqa: F401,F403

# Plugins domain models
from iotsploit_django.adapters.django.plugins.models import *  # noqa: F401,F403

# IoT fuzzer domain models
from iotsploit_django.adapters.django.iot_fuzzer.models import *  # noqa: F401,F403


