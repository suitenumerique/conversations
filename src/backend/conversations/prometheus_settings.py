"""Django configuration mixin for the Prometheus metrics (django-prometheus)."""

from configurations import values
from lasuite.configuration.values import SecretFileValue


class PrometheusSettings:
    """
    Opt-in Prometheus instrumentation, OFF by default.

    When enabled, `django_prometheus` is added to INSTALLED_APPS and its two middlewares
    wrap MIDDLEWARE (see setup_prometheus_metrics) to count and time every request,
    labelled by view name, method and status: never by path, user or conversation.

    The metrics are served on /metrics, outside of /api/ so that the ingress does not
    publish them. Whoever reaches it still has to present PROMETHEUS_API_KEY as a bearer
    token (core.middleware.PrometheusAuthMiddleware), and the application refuses to
    start with the metrics enabled and no key.

    Wired by Base.setup_prometheus_metrics, which needs the settings of Base.
    """

    PROMETHEUS_METRICS_ENABLED = values.BooleanValue(
        False, environ_name="PROMETHEUS_METRICS_ENABLED", environ_prefix=None
    )
    PROMETHEUS_API_KEY = SecretFileValue(
        None, environ_name="PROMETHEUS_API_KEY", environ_prefix=None
    )
    # Let /metrics be scraped over plain http where SECURE_SSL_REDIRECT is on, for a
    # scraper that reaches the pods directly, past the proxy terminating TLS (an
    # in-cluster Prometheus). The redirect does not protect the bearer token: a scrape
    # over http has already sent it in clear when the redirect answers. A scraper that
    # crosses an untrusted network must target https itself.
    PROMETHEUS_METRICS_SSL_REDIRECT_EXEMPT = values.BooleanValue(
        False,
        environ_name="PROMETHEUS_METRICS_SSL_REDIRECT_EXEMPT",
        environ_prefix=None,
    )
    # Also count and time the SQL queries, by swapping the database engine for
    # django-prometheus' instrumented subclass of it.
    PROMETHEUS_DB_METRICS_ENABLED = values.BooleanValue(
        True, environ_name="PROMETHEUS_DB_METRICS_ENABLED", environ_prefix=None
    )
    # uvicorn runs several worker processes and a scrape is answered by one of them:
    # they all write their numbers to this directory so that whichever answers can add
    # them up. It must be the same for every worker, hence a fixed default (in the
    # system temporary directory, named after the user) rather than a random one.
    PROMETHEUS_MULTIPROC_DIR = values.Value(
        None, environ_name="PROMETHEUS_MULTIPROC_DIR", environ_prefix=None
    )
