def test_import_iotsploit_django():
    import iotsploit_django  # noqa: F401


def test_import_settings_dev():
    from iotsploit_django.settings import dev as _dev  # noqa: F401


def test_import_urls_without_django_setup():
    # Should not trigger Django AppRegistry errors.
    import iotsploit_django.urls  # noqa: F401





def test_device_driver_manager_is_built_only_in_composition_roots():
    """The manager is a process-wide singleton, so a second builder is a bug.

    `__init__` no-ops after the first construction: whoever builds it first
    fixes the plugin root for the process. A builder that does not read the
    operator's configured root therefore hides a filesystem driver from every
    later caller, depending only on which request arrived first.
    """
    import pathlib
    import re

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    allowed = {
        "iotsploit-django/src/iotsploit_django/composition_root/core_container.py",
        "iotsploit-mcp/src/iotsploit_mcp/composition_root.py",
    }

    builders = set()
    for path in repo_root.glob("iotsploit-*/src/**/*.py"):
        if re.search(r"\bDeviceDriverManager\(", path.read_text(encoding="utf-8")):
            builders.add(path.relative_to(repo_root).as_posix())

    assert builders == allowed, f"unexpected DeviceDriverManager builders: {sorted(builders - allowed)}"
