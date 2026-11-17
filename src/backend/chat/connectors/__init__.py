"""MCP connectors: remote servers a user has switched on for themselves."""

from chat.connectors.base import Connector, ConnectorSpec
from chat.connectors.datagouv import DATAGOUV_SPEC, DataGouvConnector
from chat.connectors.registry import CONNECTOR_CLASSES, connectors_for_user
from chat.connectors.toolset import (
    CONNECTOR_UNAVAILABLE_ERRORS,
    ConnectorToolset,
    enter_mcp_toolsets,
    is_connector_unreachable,
)

__all__ = [
    "CONNECTOR_CLASSES",
    "CONNECTOR_UNAVAILABLE_ERRORS",
    "DATAGOUV_SPEC",
    "Connector",
    "ConnectorSpec",
    "ConnectorToolset",
    "DataGouvConnector",
    "connectors_for_user",
    "enter_mcp_toolsets",
    "is_connector_unreachable",
]
