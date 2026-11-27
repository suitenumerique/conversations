"""The registry: the only reader of the `MCP_CONNECTORS` setting.

`MCP_CONNECTORS` is a JSON list with one object per connector (see
docs/tools.md, "Declaring a connector"). The same validation serves two callers:

- `chat.checks` turns every problem into a `chat.E101` error, so a deployment
  with a declaration it cannot use fails `manage.py check` (and `migrate`).
- `declared_connectors` logs each problem and leaves that declaration out, so a
  running instance survives a typo: one bad connector never costs every user
  their turn.

Either way a declaration that cannot be fully validated is never offered, not
even with a weaker setting.
"""

import json
from collections import Counter
from typing import Any

from django.conf import settings

import structlog

from core.feature_flags.flags import FeatureToggle

from chat.connectors.definition import ConnectorDefinition

# Not __name__: the name connector log lines have always had.
logger = structlog.get_logger("chat.mcp_servers")


def _feature_flag_problem(definition: ConnectorDefinition) -> str | None:
    """Why the cohort flag cannot be read, or None when it can.

    Resolved the way the cohort check resolves it, so a flag accepted here is
    one `is_feature_enabled` can answer for. An unknown flag is refused rather
    than read as "everyone".
    """
    if definition.feature_flag is None:
        return None
    try:
        value = getattr(settings.FEATURE_FLAGS, definition.feature_flag)
    except AttributeError:
        value = None
    # The model's own attributes (`copy`, `model_dump`, `__class__`...) resolve
    # too; only a toggle is something the cohort check can read.
    if not isinstance(value, FeatureToggle):
        return (
            f"Connector {definition.slug!r}: unknown feature_flag "
            f"{definition.feature_flag!r}, expected a FeatureFlags field."
        )
    return None


def _raw_declarations() -> tuple[list[Any] | None, str | None]:
    """The declared list, or None and why it could not be read."""
    value = getattr(settings, "MCP_CONNECTORS", "[]")
    if isinstance(value, str):
        if not value.strip():
            return [], None
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            return None, f"MCP_CONNECTORS is not valid JSON: {error}."
    if not isinstance(value, list):
        return None, "MCP_CONNECTORS must be a JSON list, one object per connector."
    return value, None


def _validate() -> tuple[list[ConnectorDefinition], list[tuple[str | None, str]]]:
    """Usable connectors in declaration order, and (slug, problem) for the rest.

    A slug declared twice refuses every declaration of it: neither can be told
    to be the intended one. So do two slugs whose tool prefixes overlap (`geo`
    and `geo_ign`): their servers could publish the same tool name, which ends
    the agent run.
    """
    raw, problem = _raw_declarations()
    if raw is None:
        return [], [(None, problem)]

    problems = []
    definitions = []
    for declaration in raw:
        slug = declaration.get("slug") if isinstance(declaration, dict) else None
        try:
            definition = ConnectorDefinition.from_dict(declaration)
        except ValueError as error:
            problems.append((slug, str(error)))
            continue
        if flag_problem := _feature_flag_problem(definition):
            problems.append((slug, flag_problem))
            continue
        definitions.append(definition)

    # Only string slugs: anything else was refused above, and may not be hashable.
    counts = Counter(
        declaration["slug"]
        for declaration in raw
        if isinstance(declaration, dict) and isinstance(declaration.get("slug"), str)
    )
    refused = {slug for slug, count in counts.items() if count > 1}
    for slug in sorted(refused):
        problems.append((slug, f"Connector slug {slug!r} is declared more than once (duplicate)."))

    slugs = sorted({definition.slug for definition in definitions} - refused)
    for first in slugs:
        for second in slugs:
            if second.startswith(f"{first}_"):
                refused |= {first, second}
                problems.append(
                    (
                        first,
                        f"Connector slugs {first!r} and {second!r} overlap: tools "
                        f"prefixed {first!r} and {second!r} could share a name.",
                    )
                )

    return [d for d in definitions if d.slug not in refused], problems


def read_declarations() -> tuple[list[ConnectorDefinition], list[str]]:
    """Every usable connector, in declaration order, and what is wrong with the rest."""
    definitions, problems = _validate()
    return definitions, [problem for _slug, problem in problems]


def declared_connectors() -> list[ConnectorDefinition]:
    """Every connector the deployment declares and the registry accepts.

    Read again on every call, so a change of declaration takes effect on the
    next turn. Each refused declaration is logged on every read: a running
    instance keeps saying what `chat.E101` would have stopped at startup.
    """
    definitions, problems = _validate()
    for slug, problem in problems:
        logger.error(
            "connector_declaration_refused",
            connector_id=slug if isinstance(slug, str) else None,
            reason=problem,
        )
    return definitions
