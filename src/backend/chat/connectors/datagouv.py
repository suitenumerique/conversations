"""What still knows data.gouv by name: its slug and its opt-in field.

data.gouv itself is declared in `MCP_CONNECTORS` like any other connector. Only
the opt-in remains its own: #985 replaces `user_opted_in` with
`User.allowed_connectors`.
"""

from core.models import User

from chat.connectors.definition import ConnectorDefinition

# The connector's name in code, events, analytics and tool names, never shown to
# a user. Mirrored by the frontend, which reads it off the notice. Must not
# change: opt-ins and history are keyed on it.
DATAGOUV_SLUG = "datagouv"


def user_opted_in(user: User, definition: ConnectorDefinition) -> bool:
    """Whether the user gave their standing consent to this connector.

    Only data.gouv has an opt-in field so far; any other connector has none
    until #985 makes the opt-in a list of slugs, and is used only when forced.
    """
    return definition.slug == DATAGOUV_SLUG and user.allow_datagouv_connector
