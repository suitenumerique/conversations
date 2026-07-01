"""Tests for chat admin classes."""

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache

import pytest

from chat.admin import ModelHealthAdmin
from chat.model_health import model_health_cache_key
from chat.models import ModelHealth


@pytest.mark.django_db
def test_model_health_admin_save_updates_cache(clear_cache):  # pylint: disable=unused-argument
    """Editing a status in the admin mirrors the new value into the Redis cache."""
    key = model_health_cache_key("albert", "some-model")
    obj = ModelHealth.objects.create(provider="albert", model_id="some-model", status="green")
    cache.set(key, "green", timeout=None)

    obj.status = "red"
    admin_instance = ModelHealthAdmin(ModelHealth, AdminSite())
    admin_instance.save_model(request=None, obj=obj, form=None, change=True)

    assert ModelHealth.objects.get(pk=obj.pk).status == "red"
    assert cache.get(key) == "red"
