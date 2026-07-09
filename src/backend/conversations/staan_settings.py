"""Django configuration mixin for Staan settings."""

from configurations import values


class StaanSettings:
    """Staan settings for web_search_staan tool."""

    STAAN_API_KEY = values.Value(
        default=None,
        environ_name="STAAN_API_KEY",
        environ_prefix=None,
    )
    STAAN_API_TIMEOUT = values.IntegerValue(
        default=20,
        environ_name="STAAN_API_TIMEOUT",
        environ_prefix=None,
    )
    STAAN_SEARCH_ENDPOINT = values.Value(
        default="https://api.staan.ai/v2/search/web",
        environ_name="STAAN_SEARCH_ENDPOINT",
        environ_prefix=None,
    )
    STAAN_SEARCH_MARKET = values.Value(
        default="fr-fr",
        environ_name="STAAN_SEARCH_MARKET",
        environ_prefix=None,
    )
    STAAN_SEARCH_EXTRA_SNIPPETS = values.BooleanValue(
        default=True,
        environ_name="STAAN_SEARCH_EXTRA_SNIPPETS",
        environ_prefix=None,
    )
    STAAN_MAX_RESULTS = values.IntegerValue(
        default=10,
        environ_name="STAAN_MAX_RESULTS",
        environ_prefix=None,
    )
    STAAN_MAX_SNIPPET_LENGTH = values.IntegerValue(
        default=5000,
        help_text="Maximum length of the snippets per url to return (in characters)",
        environ_name="STAAN_MAX_SNIPPET_LENGTH",
        environ_prefix=None,
    )
