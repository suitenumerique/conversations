"""Which connectors this deployment offers: the registry.

Connectors are declared as data, in the `MCP_CONNECTORS` setting (a JSON list
of objects, see `ConnectorDefinition.from_dict` and docs/tools.md), plus
data.gouv from its own legacy settings. Adding a connector is a configuration
change: no code, no migration.

`connector_definitions` is what the rest of the code reads. It is lenient: a
declaration it cannot use is logged and left out, because a typo in one
connector must not cost every user their turn. `validate_connector_declarations`
is the strict counterpart, run as a Django system check so the same mistake
fails `manage.py check` and the deployment's startup instead.
"""

from django.conf import settings
from django.core import checks

import structlog
from cryptography.fernet import Fernet

from chat.connectors.datagouv import datagouv_definition
from chat.connectors.definition import ConnectorDefinition

logger = structlog.get_logger(__name__)


def _declared() -> tuple[list[ConnectorDefinition], list[str]]:
    """Every declared connector, and every reason a declaration was refused."""
    definitions: list[ConnectorDefinition] = []
    errors: list[str] = []

    if (datagouv := datagouv_definition()) is not None:
        definitions.append(datagouv)

    declarations = settings.MCP_CONNECTORS
    if not isinstance(declarations, list):
        return definitions, [f"MCP_CONNECTORS must be a JSON list, not {type(declarations)}."]

    for declaration in declarations:
        try:
            definitions.append(ConnectorDefinition.from_dict(declaration))
        except (ValueError, TypeError) as error:
            errors.append(str(error))

    usable: list[ConnectorDefinition] = []
    seen: set[str] = set()
    for definition in definitions:
        if definition.slug in seen:
            errors.append(f"Connector slug {definition.slug!r} is declared twice.")
            continue
        if not definition.auth.supported:
            errors.append(
                f"Connector {definition.slug!r} needs {definition.auth.kind} "
                "authentication, which is not implemented yet."
            )
            continue
        if (problem := _oauth_problem(definition)) is not None:
            errors.append(problem)
            continue
        if definition.feature_flag is not None and not _is_known_flag(definition.feature_flag):
            errors.append(
                f"Connector {definition.slug!r} names an unknown feature flag "
                f"{definition.feature_flag!r}."
            )
            continue
        seen.add(definition.slug)
        usable.append(definition)

    return usable, errors


def _oauth_problem(definition: ConnectorDefinition) -> str | None:
    """Why a per-user OAuth connector could not work here, or None."""
    auth = definition.auth
    if not auth.needs_linking:
        return None
    try:
        Fernet(settings.CONNECTORS_TOKEN_ENCRYPTION_KEY)
    except TypeError, ValueError:
        return (
            f"Connector {definition.slug!r} stores user tokens: set "
            "CONNECTORS_TOKEN_ENCRYPTION_KEY to a Fernet key."
        )
    if auth.client_secret_env and auth.client_secret is None:
        return (
            f"Connector {definition.slug!r} reads its client secret from "
            f"{auth.client_secret_env}, which is not set."
        )
    return None


def _is_known_flag(name: str) -> bool:
    """Whether `name` is a feature flag `is_feature_enabled` can read."""
    try:
        getattr(settings.FEATURE_FLAGS, name)
    except AttributeError:
        return False
    return True


def connector_definitions() -> dict[str, ConnectorDefinition]:
    """The connectors this deployment offers, by slug, in declaration order.

    Read from settings on every call, so tests may override them; the parsing
    is cheap next to anything a turn does with the result.
    """
    definitions, errors = _declared()
    for error in errors:
        logger.error("connector_declaration_refused", reason=error)
    return {definition.slug: definition for definition in definitions}


def get_connector_definition(slug: str) -> ConnectorDefinition | None:
    """One offered connector, or None."""
    return connector_definitions().get(slug)


def validate_connector_declarations() -> list[str]:
    """Every reason a declaration would be refused; empty when all are usable."""
    return _declared()[1]


@checks.register(checks.Tags.compatibility)
def check_connector_declarations(app_configs=None, **kwargs):
    """Fail startup on a connector declaration the registry would leave out."""
    del app_configs, kwargs
    return [
        checks.Error(error, hint="See MCP_CONNECTORS in docs/env.md.", id="chat.E101")
        for error in validate_connector_declarations()
    ]
