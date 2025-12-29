def test_import_iotsploit_django():
    import iotsploit_django  # noqa: F401


def test_import_settings_dev():
    from iotsploit_django.settings import dev as _dev  # noqa: F401


def test_import_urls_without_django_setup():
    # Should not trigger Django AppRegistry errors.
    import iotsploit_django.urls  # noqa: F401



