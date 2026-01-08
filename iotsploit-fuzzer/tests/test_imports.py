import importlib


def test_import_iotsploit_fuzzer():
    import iotsploit_fuzzer  # noqa: F401


def test_common_modules_import():
    modules = [
        "iotsploit_fuzzer.core.orchestrator",
        "iotsploit_fuzzer.core.fuzzing_engine",
        "iotsploit_fuzzer.generators.base",
        "iotsploit_fuzzer.harnesses.base",
        "iotsploit_fuzzer.monitoring.monitor",
    ]
    for m in modules:
        importlib.import_module(m)


