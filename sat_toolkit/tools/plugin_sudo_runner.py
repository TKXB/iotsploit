"""sat_toolkit.tools.plugin_sudo_runner

CLI helper that runs a single SAT exploit plugin. Designed to be executed
under *sudo* by PrivilegeManager.run_plugin_with_sudo so that the main Django
process does not need to escalate privileges.

Environment variables used:
    TASK_ID       – Unique task ID for storing result in Redis
    TARGET_JSON   – JSON-encoded target dictionary (optional)
    PARAMS_JSON   – JSON-encoded parameters dictionary (optional)

Usage:
    sudo -E env TASK_ID='uuid' TARGET_JSON='{}' PARAMS_JSON='{}' python -m sat_toolkit.tools.plugin_sudo_runner syn_flood_attack
"""

from __future__ import annotations

import os
import json
import sys
import logging
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Bootstrap Django project (if used inside the SAT server environment)
# ---------------------------------------------------------------------------
DJANGO_SETTINGS = os.environ.get("DJANGO_SETTINGS_MODULE", "sat_django_entry.settings")
if DJANGO_SETTINGS:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS)
    try:
        import django
        django.setup()
    except Exception:  # pragma: no cover
        # If Django is not available, continue – the exploit manager may still work
        pass

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_json_env(name: str) -> Dict[str, Any]:
    env_value = os.getenv(name, "{}")
    logger.debug(f"[sudo-runner] Raw environment variable {name}: {repr(env_value)}")
    try:
        parsed = json.loads(env_value)
        logger.debug(f"[sudo-runner] Successfully parsed {name}: {parsed}")
        return parsed
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s (raw value: %s)", name, e, repr(env_value))
        return {}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m sat_toolkit.tools.plugin_sudo_runner <plugin_name>", file=sys.stderr)
        sys.exit(1)

    plugin_name = sys.argv[1]
    task_id = os.getenv("TASK_ID")
    target = load_json_env("TARGET_JSON")
    parameters = load_json_env("PARAMS_JSON")

    if not task_id:
        print("ERROR: TASK_ID environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    logger.info(f"[sudo-runner] Received task_id: {task_id}")
    logger.info(f"[sudo-runner] Plugin name: {plugin_name}")
    logger.info(f"[sudo-runner] Target: {target}")
    logger.info(f"[sudo-runner] Parameters: {parameters}")

    try:
        from sat_toolkit.adapters.django.exploit_manager_factory import get_exploit_plugin_manager
        from iotsploit_core.core.exploit_spec import ExploitResult
        import redis
        from django.conf import settings
    except ImportError as e:  # pragma: no cover
        print(f"Failed to import required modules: {e}", file=sys.stderr)
        sys.exit(2)

    # Connect to Redis using Django settings
    try:
        redis_client = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            db=getattr(settings, 'REDIS_DB', 0)
        )
        # Test Redis connection
        redis_client.ping()
    except Exception as e:
        print(f"Failed to connect to Redis: {e}", file=sys.stderr)
        sys.exit(3)

    # Redirect all logging to stderr to keep stdout clean
    import logging
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )

    # This process is already running with elevated privileges; execute in-process.
    mgr = get_exploit_plugin_manager(use_celery=False)
    mgr.initialize()

    logger.info("[sudo-runner] REDIS VERSION - Executing plugin '%s' with target=%s params=%s (task_id=%s)", 
                plugin_name, target, parameters, task_id)
    
    try:
        result = mgr.execute_plugin(plugin_name, target=target, parameters=parameters)

        # Serialize result (ExploitResult or dict/other)
        def _default(o):
            if isinstance(o, set):
                return list(o)
            if hasattr(o, "__dict__"):
                return o.__dict__
            return str(o)

        try:
            result_json = json.dumps(result if isinstance(result, dict) else result.__dict__, default=_default)
        except Exception as e:
            # Fallback serialization
            result_json = json.dumps({"success": False, "message": f"Serialization error: {str(e)}"})

        # Store result in Redis with expiration (5 minutes)
        result_key = f"plugin_result:{task_id}"
        
        # Check if key already exists before storing
        existing_data = redis_client.get(result_key)
        if existing_data:
            logger.warning(f"[sudo-runner] Key {result_key} already exists! Existing data: {existing_data.decode('utf-8')[:100]}...")
        
        redis_client.setex(result_key, 300, result_json)  # 300 seconds = 5 minutes
        
        # Verify the data was stored correctly
        stored_data = redis_client.get(result_key)
        if stored_data:
            logger.info(f"[sudo-runner] Successfully stored result in Redis (key={result_key}): {stored_data.decode('utf-8')[:100]}...")
        else:
            logger.error(f"[sudo-runner] Failed to store result in Redis (key={result_key})")
        
        logger.info("[sudo-runner] Plugin execution completed, result stored in Redis (key=%s)", result_key)
        
        # Print success message to stdout (for debugging)
        print(f"Plugin execution completed successfully. Result stored in Redis with key: {result_key}")
        
    except Exception as e:
        logger.error("[sudo-runner] Plugin execution failed: %s", str(e))
        
        # Store error result in Redis
        error_result = json.dumps({"success": False, "message": f"Plugin execution failed: {str(e)}"})
        result_key = f"plugin_result:{task_id}"
        redis_client.setex(result_key, 300, error_result)
        
        print(f"Plugin execution failed. Error stored in Redis with key: {result_key}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main() 