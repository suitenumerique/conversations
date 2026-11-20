"""MCP connectors: remote servers a user has switched on for themselves.

- `definition`: what a connector is, as an immutable value.
- `auth`: how we authenticate to a connector (anonymous only, for now).
- `registry`: which connectors the deployment offers (`MCP_CONNECTORS`, plus
  data.gouv from its legacy settings).
- `turn`: the connectors' state for one turn, one by one and as a group.
- `errors`: how a connector we cannot reach shows up.
- `runtime`: the turn-time toolset wrapper and how toolsets are entered.
- `datagouv`: the data.gouv.fr definition, built from its deployment settings.
"""

from chat.connectors.auth import AuthKind, ConnectorAuth
from chat.connectors.datagouv import DATAGOUV_SLUG, datagouv_definition
from chat.connectors.definition import ConnectorDefinition, Tier
from chat.connectors.errors import CONNECTOR_UNAVAILABLE_ERRORS, is_connector_unreachable
from chat.connectors.registry import connector_definitions, get_connector_definition
from chat.connectors.runtime import ConnectorToolset, enter_mcp_toolsets
from chat.connectors.turn import TurnConnectors, UserConnector

__all__ = [
    "CONNECTOR_UNAVAILABLE_ERRORS",
    "DATAGOUV_SLUG",
    "AuthKind",
    "ConnectorAuth",
    "ConnectorDefinition",
    "ConnectorToolset",
    "Tier",
    "TurnConnectors",
    "UserConnector",
    "connector_definitions",
    "datagouv_definition",
    "enter_mcp_toolsets",
    "get_connector_definition",
    "is_connector_unreachable",
]
