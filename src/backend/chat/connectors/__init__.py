"""MCP connectors: remote servers whose tools the agent may use for a user.

- `definition`: what a connector is, as frozen data (`ConnectorDefinition`, `Tier`).
- `turn`: one user's connectors for one turn (`UserConnector`, `TurnConnectors`).
- `runtime`: the toolset the agent sees, and how it is entered.
- `errors`: how an unreachable server shows itself.
- `registry`: the declarations in `MCP_CONNECTORS`, validated.
- `datagouv`: data.gouv's slug and opt-in field, until `allowed_connectors` (#985).

See docs/adr/0001-connector-trust-tiers.md.
"""

from chat.connectors.definition import ConnectorDefinition, Tier

__all__ = ["ConnectorDefinition", "Tier"]
