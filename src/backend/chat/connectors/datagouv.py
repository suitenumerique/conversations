"""The data.gouv.fr connector: one spec, no new state machine.

Everything that makes data.gouv data.gouv — its endpoint settings, its cohort
flag, its opt-in column, and the words the model reads about it — lives in
`DATAGOUV_SPEC`. `DataGouvConnector` only fixes that spec onto the generic
`Connector`, and keeps the historical class-level `connector_id`.
"""

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from core.models import User

from chat.connectors.base import Connector, ConnectorSpec

DATAGOUV_SPEC = ConnectorSpec(
    connector_id="datagouv",
    url_setting="DATAGOUV_CONNECTOR_URL",
    init_timeout_setting="DATAGOUV_CONNECTOR_INIT_TIMEOUT",
    read_timeout_setting="DATAGOUV_CONNECTOR_READ_TIMEOUT",
    feature_flag="datagouv_connector",
    opt_in_attribute="allow_datagouv_connector",
    unavailable_tool_message=(
        "data.gouv.fr could not be reached. Do not call its tools again for this request."
    ),
    available_instruction=(
        "The data.gouv.fr tools search France's open-data catalogue: datasets, "
        "the organisations that publish them, and public APIs. Use them when the "
        "answer depends on official French public data (statistics, registries, "
        "local facilities, prices, figures for a commune or département), or "
        "when the user asks for a dataset, a file or an API. Prefer them over "
        "answering such figures from memory. Do not use them for questions about "
        "other countries, general knowledge, administrative procedures, "
        "writing or coding tasks, or "
        "questions about the user's attached documents."
    ),
    forced_instruction="You must use the data.gouv.fr tools before answering the user request.",
    unreachable_instruction=(
        "data.gouv.fr could not be reached for this request. Answer "
        "from your own knowledge or other tools,"
        " and tell the user you could not "
        "consult data.gouv.fr."
    ),
)


@dataclass
class DataGouvConnector(Connector):
    """The data.gouv.fr connector's state for one turn. See `Connector`."""

    # The connector's name in code, events and tool names, never shown to a
    # user. Mirrored by the frontend, which reads it off the notice.
    connector_id: ClassVar[str] = DATAGOUV_SPEC.connector_id

    # Narrowed on purpose: this connector's spec is fixed, so callers and the
    # registry never pass one. New connectors subclass with their own spec.
    @classmethod
    def for_user(  # pylint: disable=arguments-differ
        cls, user: User, conversation_pk: UUID
    ) -> "DataGouvConnector":
        """The connector as it stands for this user, before the turn says anything."""
        return super().for_user(user, conversation_pk, DATAGOUV_SPEC)
