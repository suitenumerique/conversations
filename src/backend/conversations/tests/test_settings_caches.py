"""Tests for the Redis cache settings."""

from django_redis.pool import ConnectionFactory

from conversations.settings import Production


def test_production_cache_has_socket_timeouts():
    """A hung Redis must fail cache calls quickly instead of blocking every request."""
    options = Production.CACHES["default"]["OPTIONS"]

    params = ConnectionFactory(options).make_connection_params("redis://redis:6379/1")

    assert params["socket_timeout"] == 1
    assert params["socket_connect_timeout"] == 0.5
