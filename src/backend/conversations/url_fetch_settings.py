"""Django configuration mixin for URL fetch settings."""

from configurations import values


class UrlFetchSettings:
    """Settings for the url_fetch tool."""

    URL_FETCH_BLOCKED_SCHEMES = values.ListValue(
        default=["http"],
        environ_name="URL_FETCH_BLOCKED_SCHEMES",
        environ_prefix=None,
    )
    URL_FETCH_BLOCKED_HOSTS = values.ListValue(
        default=["localhost", "127.0.0.1", "0.0.0.0", "::1"],  # noqa: S104
        environ_name="URL_FETCH_BLOCKED_HOSTS",
        environ_prefix=None,
    )
    URL_FETCH_BLOCKED_TLDS = values.ListValue(
        default=[".ru", ".cn", ".kp", ".ir"],
        environ_name="URL_FETCH_BLOCKED_TLDS",
        environ_prefix=None,
    )
