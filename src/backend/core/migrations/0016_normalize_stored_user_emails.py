"""Normalize stored user emails to ASCII lowercase, so identity lookups can match them exactly.

Users whose emails only differ by case are kept and end up sharing the normalized email:
merging them cannot be undone. The OIDC email fallback then logs in the active one, and
refuses the login when several of them are active.
"""

import string

from django.db import migrations

_ASCII_LOWERCASE_TABLE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def normalize_email(email):
    """Strip ASCII whitespace around an email and lowercase its ASCII letters only."""
    if not email:
        return email
    return email.strip(string.whitespace).translate(_ASCII_LOWERCASE_TABLE)


BATCH_SIZE = 500


def forwards(apps, schema_editor):
    """ASCII-lowercase the emails stored on users, flushing updates in bounded batches."""
    user_model = apps.get_model("core", "User")
    to_update = []
    for user in user_model.objects.only("id", "email").iterator(chunk_size=BATCH_SIZE):
        normalized = normalize_email(user.email)
        if normalized != user.email:
            user.email = normalized
            to_update.append(user)
        if len(to_update) >= BATCH_SIZE:
            user_model.objects.bulk_update(to_update, ["email"], batch_size=BATCH_SIZE)
            to_update = []
    if to_update:
        user_model.objects.bulk_update(to_update, ["email"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_user_allow_datagouv_connector"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
