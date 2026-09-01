"""iotsploit_django.tools.plugin_sudo_runner

CLI helper that runs a single SAT exploit plugin. Designed to be executed
under *sudo* by PrivilegeManager.run_plugin_with_sudo so that the main Django
process does not need to escalate privileges.

Environment variables used:
    RESULT_PATH   – Path for the single JSON result document
    TARGET_JSON   – JSON-encoded target dictionary (optional)
    PARAMS_JSON   – JSON-encoded parameters dictionary (optional)

Usage:
    sudo -E env RESULT_PATH='/tmp/result.json' TARGET_JSON='{}' PARAMS_JSON='{}' python -m iotsploit_django.tools.plugin_sudo_runner syn_flood_attack
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
DJANGO_SETTINGS = os.environ.get("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
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
        print("Usage: python -m iotsploit_django.tools.plugin_sudo_runner <plugin_name>", file=sys.stderr)
        sys.exit(1)

    plugin_name = sys.argv[1]
    result_path = os.getenv("RESULT_PATH")
    target = load_json_env("TARGET_JSON")
    parameters = load_json_env("PARAMS_JSON")

    if not result_path:
        print("ERROR: RESULT_PATH environment variable is required", file=sys.stderr)
        sys.exit(1)

    logger.info(f"[sudo-runner] Plugin name: {plugin_name}")
    logger.info(f"[sudo-runner] Target: {target}")
    logger.info(f"[sudo-runner] Parameters: {parameters}")

    try:
        from iotsploit_django.adapters.django.exploit_manager_factory import get_exploit_plugin_manager
    except ImportError as e:  # pragma: no cover
        print(f"Failed to import required modules: {e}", file=sys.stderr)
        sys.exit(2)

    # This process is already running with elevated privileges; execute in-process.
    mgr = get_exploit_plugin_manager()
    mgr.initialize()

    logger.info("[sudo-runner] Executing plugin '%s' with target=%s params=%s", plugin_name, target, parameters)
    
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

        with open(result_path, "w", encoding="utf-8") as result_file:
            result_file.write(result_json)
        logger.info("[sudo-runner] Plugin execution completed")
        
    except Exception as e:
        logger.error("[sudo-runner] Plugin execution failed: %s", str(e))
        
        print(f"Plugin execution failed: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
