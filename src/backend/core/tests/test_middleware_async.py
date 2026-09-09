"""Regression coverage for the ASGI "CancelledError exception in shielded future" noise.

We serve the app with uvicorn (ASGI). A sync-only middleware forces asgiref to
run the downstream chain in a shielded worker thread (``sync_to_async`` +
``asyncio.shield``); when a client disconnects mid-request (frequent on the
streaming chat endpoint) the resulting CancelledError lands on that shielded
future and asgiref logs "CancelledError exception in shielded future".

Two complementary checks:

* ``test_all_configured_middleware_are_async_capable`` — static invariant guard:
  no MIDDLEWARE entry may be sync-only (the condition that creates the shield).
* ``test_maintenance_middleware_adapts_to_async_downstream`` — behavioural proof
  on our own middleware: with an async downstream it is itself adapted to a
  coroutine, so Django never wraps it (or the chain below it) in ``sync_to_async``.
"""

import inspect

from django.conf import settings
from django.utils.module_loading import import_string

from core.middleware import MaintenanceMiddleware


def test_all_configured_middleware_are_async_capable():
    """No entry in MIDDLEWARE may be sync-only."""
    sync_only = [
        dotted_path
        for dotted_path in settings.MIDDLEWARE
        if not getattr(import_string(dotted_path), "async_capable", False)
    ]
    assert not sync_only, (
        f"Sync-only middleware would force a shielded sync boundary under ASGI: {sync_only}"
    )


def test_maintenance_middleware_adapts_to_async_downstream():
    """With an async downstream, the middleware is itself a coroutine function.

    Django only wraps a middleware in ``sync_to_async`` (the shielded boundary)
    when it cannot run async next to an async handler. A middleware that reports
    as a coroutine function is called via its native ``__acall__`` path instead,
    so no shield is introduced around it or the chain below it.
    """

    async def async_get_response(request):  # pragma: no cover - never awaited here
        return None

    middleware = MaintenanceMiddleware(async_get_response)

    assert inspect.iscoroutinefunction(middleware)
