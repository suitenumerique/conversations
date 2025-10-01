"""Django configuration mixin for Brave settings."""

from configurations import values


class BraveSettings:
    """Brave settings for web_search_brave tool."""

    BRAVE_API_KEY = values.Value(
        default=None,
        environ_name="BRAVE_API_KEY",
        environ_prefix=None,
    )
    BRAVE_API_TIMEOUT = values.IntegerValue(
        default=5,
        environ_name="BRAVE_API_TIMEOUT",
        environ_prefix=None,
    )

    # Search
    BRAVE_SEARCH_COUNTRY = values.Value(
        default=None,
        environ_name="BRAVE_SEARCH_COUNTRY",
        environ_prefix=None,
    )
    BRAVE_SEARCH_LANG = values.Value(
        default=None,
        environ_name="BRAVE_SEARCH_LANG",
        environ_prefix=None,
    )
    BRAVE_MAX_RESULTS = values.IntegerValue(
        default=10,
        environ_name="BRAVE_MAX_RESULTS",
        environ_prefix=None,
    )
    BRAVE_SEARCH_SAFE_SEARCH = values.Value(
        default="moderate",
        environ_name="BRAVE_SEARCH_SAFE_SEARCH",
        environ_prefix=None,
    )  # off, moderate, strict
    BRAVE_SEARCH_SPELLCHECK = values.BooleanValue(
        default=True,
        environ_name="BRAVE_SEARCH_SPELLCHECK",
        environ_prefix=None,
    )
    BRAVE_SEARCH_EXTRA_SNIPPETS = values.BooleanValue(
        default=True,
        environ_name="BRAVE_SEARCH_EXTRA_SNIPPETS",
        environ_prefix=None,
    )
