"""Deprecated: the connector code moved to `chat.connectors`.

Re-exports four runtime names for one release: `ConnectorToolset`,
`enter_mcp_toolsets`, `is_connector_unreachable` and
`CONNECTOR_UNAVAILABLE_ERRORS`. Import them from `chat.connectors.runtime` and
`chat.connectors.errors` instead. `DataGouvConnector` and `UNREACHABLE_MESSAGE`
are gone: see `chat.connectors.turn` and `ConnectorDefinition`.
"""

from chat.connectors.errors import CONNECTOR_UNAVAILABLE_ERRORS, is_connector_unreachable
from chat.connectors.runtime import ConnectorToolset, enter_mcp_toolsets

__all__ = [
    "CONNECTOR_UNAVAILABLE_ERRORS",
    "ConnectorToolset",
    "enter_mcp_toolsets",
    "is_connector_unreachable",
]
