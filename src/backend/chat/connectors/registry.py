"""The connector registry: every connector the turns may use.

Adding a connector registers its class here. Everything else — the agent
service, the event mapper — reads this, so no other code names one connector.
"""

from uuid import UUID

from core.models import User

from chat.connectors.base import Connector
from chat.connectors.datagouv import DataGouvConnector

#: Every connector class a turn may use, in the order their toolsets attach.
CONNECTOR_CLASSES: tuple[type[Connector], ...] = (DataGouvConnector,)


def connectors_for_user(user: User, conversation_pk: UUID) -> dict[str, Connector]:
    """One per-turn connector per registered class, keyed by connector id."""
    connectors = {}
    for cls in CONNECTOR_CLASSES:
        connector = cls.for_user(user, conversation_pk)
        connectors[connector.spec.connector_id] = connector
    return connectors
