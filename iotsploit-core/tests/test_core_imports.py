import importlib


def test_core_imports():
    # smoke: core + domain + ports should import in a standalone env
    import iotsploit_core  # noqa: F401

    modules = [
        'iotsploit_core.domain.device',
        'iotsploit_core.domain.plugin',
        'iotsploit_core.domain.execution_plan',
        'iotsploit_core.domain.stream',
        'iotsploit_core.ports.task_runner',
        'iotsploit_core.ports.plugin_repo',
        'iotsploit_core.ports.driver_state_repo',
        'iotsploit_core.ports.stream_backend',
        'iotsploit_core.core.base_plugin',
        'iotsploit_core.core.device_manager',
        'iotsploit_core.core.exploit_manager',
        'iotsploit_core.core.stream_manager',
    ]
    for m in modules:
        importlib.import_module(m)
