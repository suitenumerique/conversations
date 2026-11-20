"""MCP connectors: remote servers a user has switched on for themselves.

- `definition`: what a connector is, as an immutable value.
- `errors`: how a connector we cannot reach shows up.
- `runtime`: the turn-time toolset wrapper and how toolsets are entered.
- `datagouv`: the data.gouv.fr connector, built from the deployment settings.
"""

from chat.connectors.datagouv import DataGouvConnector, datagouv_definition
from chat.connectors.definition import ConnectorDefinition, Tier
from chat.connectors.errors import CONNECTOR_UNAVAILABLE_ERRORS, is_connector_unreachable
from chat.connectors.runtime import ConnectorToolset, enter_mcp_toolsets

__all__ = [
    "CONNECTOR_UNAVAILABLE_ERRORS",
    "ConnectorDefinition",
    "ConnectorToolset",
    "DataGouvConnector",
    "Tier",
    "datagouv_definition",
    "enter_mcp_toolsets",
    "is_connector_unreachable",
]
