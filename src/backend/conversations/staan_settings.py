"""Django configuration mixin for Staan settings."""

from configurations import values


class StaanSettings:
    """Staan settings for web_search_staan tool."""

    STAAN_API_KEY = values.Value(
        default=None,
        environ_name="STAAN_API_KEY",
        environ_prefix=None,
    )
    STAAN_API_TIMEOUT = values.PositiveIntegerValue(
        default=20,
        environ_name="STAAN_API_TIMEOUT",
        environ_prefix=None,
    )
    STAAN_SEARCH_EXTRA_SNIPPETS = values.BooleanValue(
        default=True,
        environ_name="STAAN_SEARCH_EXTRA_SNIPPETS",
        environ_prefix=None,
    )
    STAAN_MAX_SNIPPETS_PER_URL = values.PositiveIntegerValue(
        default=3,
        help_text=(
            "Maximum number of scored chunks the API returns per url (Staan allows 1 to 10). "
            "This is the only lever on how much text a search sends to the model: chunks are "
            "300 to 1800 characters, so a search costs roughly 10 x (1 + this) x 1000 characters."
        ),
        environ_name="STAAN_MAX_SNIPPETS_PER_URL",
        environ_prefix=None,
    )
    STAAN_MIN_SNIPPET_SCORE = values.FloatValue(
        default=0.1,
        help_text="Minimum relevance score for a chunk to be returned by the API (0 to 1)",
        environ_name="STAAN_MIN_SNIPPET_SCORE",
        environ_prefix=None,
    )
    # Kept as a literal twin of BRAVE_BLOCKED_DOMAINS (same default list) on
    # purpose: settings modules must not import chat.tools.utils, which pulls
    # Django models. The parsing/matching/filtering logic itself lives once in
    # chat.tools.utils and is shared by both backends.
    STAAN_BLOCKED_DOMAINS = values.Value(
        default=(
            "facebook.com,instagram.com,tiktok.com,twitter.com,x.com,"
            "linkedin.com,pinterest.com,snapchat.com,threads.com,threads.net"
        ),
        environ_name="STAAN_BLOCKED_DOMAINS",
        environ_prefix=None,
    )
