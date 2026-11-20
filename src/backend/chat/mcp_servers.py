"""Deprecated: import from `chat.connectors` instead.

Kept for one release so that out-of-tree imports keep working. It only
re-exports; nothing in this repository imports from here. `DataGouvConnector`
and `UNREACHABLE_MESSAGE` are gone: every connector is now a `UserConnector`,
and its unreachable message comes from its definition.
"""

import warnings

from chat.connectors.errors import CONNECTOR_UNAVAILABLE_ERRORS, is_connector_unreachable
from chat.connectors.runtime import ConnectorToolset, enter_mcp_toolsets

warnings.warn(
    "chat.mcp_servers is deprecated; import from chat.connectors instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CONNECTOR_UNAVAILABLE_ERRORS",
    "ConnectorToolset",
    "enter_mcp_toolsets",
    "is_connector_unreachable",
]
