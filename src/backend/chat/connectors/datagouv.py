"""The data.gouv.fr connector, built from its dedicated deployment settings.

data.gouv predates `MCP_CONNECTORS` and keeps its own environment variables
(`DATAGOUV_CONNECTOR_*`) so existing deployments do not change. The registry
reads it through `datagouv_definition` alongside the declared connectors; it is
in every other respect a connector like any other.
"""

from django.conf import settings

from chat.connectors.definition import ConnectorDefinition, Tier

# The connector's name in code, events and tool names, never shown to a user.
DATAGOUV_SLUG = "datagouv"

# When the model should reach for the connector's tools. The server's
# descriptions say how to use each tool but never when. The tools come from the
# MCP server under a `datagouv_` prefix and are not known statically, so the
# instruction names the source rather than one tool.
DATAGOUV_INSTRUCTIONS = (
    "The data.gouv.fr tools search France's open-data catalogue: datasets, "
    "the organisations that publish them, and public APIs. Use them when the "
    "answer depends on official French public data (statistics, registries, "
    "local facilities, prices, figures for a commune or département), or "
    "when the user asks for a dataset, a file or an API. Prefer them over "
    "answering such figures from memory. Do not use them for questions about "
    "other countries, general knowledge, administrative procedures, "
    "writing or coding tasks, or "
    "questions about the user's attached documents."
)


def datagouv_definition() -> ConnectorDefinition | None:
    """data.gouv as a definition, or None when the deployment leaves it out.

    Read from settings on every call, so tests may override them. An empty
    `DATAGOUV_CONNECTOR_URL` keeps the connector inert: not offered, not built,
    never contacted. `0` timeouts mean no limit, which the definition spells as
    None.
    """
    if not settings.DATAGOUV_CONNECTOR_URL:
        return None
    return ConnectorDefinition(
        slug=DATAGOUV_SLUG,
        name="data.gouv.fr",
        url=settings.DATAGOUV_CONNECTOR_URL,
        tier=Tier.PARTNER,
        instructions=DATAGOUV_INSTRUCTIONS,
        init_timeout=settings.DATAGOUV_CONNECTOR_INIT_TIMEOUT or None,
        read_timeout=settings.DATAGOUV_CONNECTOR_READ_TIMEOUT or None,
        feature_flag="datagouv_connector",
    )
