"""Test the `create_demo` management command"""

from unittest import mock

from django.core.management import call_command
from django.test import override_settings

import pytest

from core import models

pytestmark = pytest.mark.django_db


@mock.patch(
    "demo.defaults.NB_OBJECTS",
    {
        "users": 10,
    },
)
@override_settings(DEBUG=True)
def test_commands_create_demo():
    """The create_demo management command should create objects as expected."""
    call_command("create_demo")

    assert models.User.objects.count() == 10
