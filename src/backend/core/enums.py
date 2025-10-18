"""Core application enums declaration."""

from django.conf import global_settings
from django.utils.translation import gettext_lazy as _

# In Django's code base, `LANGUAGES` is set by default with all supported languages.
# We can use it for the choice of languages which should not be limited to the few languages
# active in the app.
# pylint: disable=no-member
ALL_LANGUAGES = {language: _(name) for language, name in global_settings.LANGUAGES}


def get_language_name(language_code):
    """Get the language name from the language code.

    Args:
        language_code (str): The language code.

    Returns:
        str: The language name.
    """
    _language_code = language_code.lower()
    return ALL_LANGUAGES.get(_language_code, ALL_LANGUAGES.get(_language_code[:2], _language_code))
