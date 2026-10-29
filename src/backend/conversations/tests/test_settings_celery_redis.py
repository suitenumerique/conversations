"""Tests for the Celery Redis socket timeouts."""

from conversations.celery_app import app
from conversations.settings import Base


def test_celery_redis_clients_have_socket_timeouts():
    """A hung Redis must fail broker and result backend calls instead of blocking."""
    assert app.conf.redis_socket_timeout == 5
    assert app.conf.redis_socket_connect_timeout == 5
    assert app.conf.broker_transport_options == {
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
    }


def test_broker_transport_options_env_values_win():
    """Options set via CELERY_BROKER_TRANSPORT_OPTIONS keep the other timeout."""

    class TestSettings(Base):
        """Fake settings with transport options set from the environment."""

        BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 7200, "socket_timeout": 10}

    assert TestSettings().CELERY_BROKER_TRANSPORT_OPTIONS == {
        "socket_timeout": 10,
        "socket_connect_timeout": 5,
        "visibility_timeout": 7200,
    }
