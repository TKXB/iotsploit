"""Base settings for iotsploit-django (standalone).

Stage-5.5: iotsploit_django must run without importing the legacy Django entry
package at settings import time.
"""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]

SECRET_KEY = "dev-secret-key-change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

INSTALLED_APPS = [
    "channels",
    "django_extensions",
    "corsheaders",
    "csp",
    # host app
    "iotsploit_django",
    # django contrib
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
]

ROOT_URLCONF = "iotsploit_django.urls"
WSGI_APPLICATION = "iotsploit_django.wsgi.application"
ASGI_APPLICATION = "iotsploit_django.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR)],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("IOTSPLOIT_DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
    }
}

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "*"]
CORS_ALLOW_HEADERS = ["Accept", "Authorization", "Content-Type", "*"]

# CSP
CSP_DEFAULT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'", "ws:", "wss:")
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'",)
CSP_IMG_SRC = ("'self'",)

IOTSPLOIT_RUNTIME = os.getenv("IOTSPLOIT_RUNTIME", "local").strip().lower()
if IOTSPLOIT_RUNTIME not in {"local", "distributed"}:
    raise RuntimeError(
        "IOTSPLOIT_RUNTIME must be 'local' or 'distributed', "
        f"not {IOTSPLOIT_RUNTIME!r}"
    )
IOTSPLOIT_LOCAL_STANDARD_WORKERS = max(
    1, int(os.getenv("IOTSPLOIT_LOCAL_STANDARD_WORKERS", "2"))
)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

if IOTSPLOIT_RUNTIME == "distributed":
    redis_url = os.getenv(
        "REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )
    CELERY_BROKER_URL = redis_url
    CELERY_RESULT_BACKEND = redis_url
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_BROKER_CONNECTION_MAX_RETRIES = 10
    CELERY_BROKER_CONNECTION_RETRY = True
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "visibility_timeout": 3600,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
    }

# Interactive plugin execution
#
# A plugin can stop mid-run and ask the operator a typed question, and the
# Control Panel can answer it. There is no setting for this: it is simply how
# an interactive plugin runs, the same way it already works in the shell.

# Interactive runs get their own queue at concurrency 1. Waiting on an answer
# holds a worker slot without using CPU, so isolating them keeps ordinary plugin
# runs moving; concurrency 1 means only one run can be waiting at a time, which
# is what lets the Control Panel show a single unambiguous question. The
# iotsploit shell's `runserver` starts this worker alongside the ordinary one;
# to run it by hand:
#   celery -A iotsploit_django.tasks.celery_app worker -Q interactive -c 1
# Long-running monitor sessions use the same durable execution task and bound
# interaction port, but are submitted explicitly to ``streaming``. Keeping
# them off ``interactive`` means a one-hour monitor can never starve prompts.
#   celery -A iotsploit_django.tasks.celery_app worker -Q streaming
CELERY_TASK_ROUTES = {
    "iotsploit_django.tasks.interaction_tasks.run_execution_task": {
        "queue": "interactive",
    },
}

if IOTSPLOIT_RUNTIME == "local":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": (
                "iotsploit_django.adapters.django.threadsafe_channel_layer."
                "ThreadSafeInMemoryChannelLayer"
            )
        }
    }
else:
    # socket_timeout must stay clear of channels_redis' brpop_timeout (5s).
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [
                    {"host": REDIS_HOST, "port": REDIS_PORT, "socket_timeout": 30},
                ],
            },
        }
    }

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "stream": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "loggers": {
        # Channels / Daphne
        "daphne": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "channels": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "channels.layers": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        # Ports & Adapters: core uses stdlib logging; Django host wires handlers/levels.
        "iotsploit_core": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "iotsploit_django": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "iotsploit_drivers": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        # Some legacy fuzzer namespaces (if present)
        "fuzzer.orchestrator": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "fuzzer.monitor": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        "fuzzer.logger": {"handlers": ["stream"], "level": "INFO", "propagate": False},
        # Root
        "": {"level": "WARNING", "handlers": []},
    },
}
