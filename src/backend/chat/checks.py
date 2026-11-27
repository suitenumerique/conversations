"""System checks of the chat application."""

from django.core import checks

from chat.connectors.registry import read_declarations

# Helm's wait-for-the-database loop connects without running system checks, so
# a configuration error is reported by the migrate command after it instead of
# keeping the loop waiting forever.
CONNECTORS_TAG = "connectors"


@checks.register(CONNECTORS_TAG)
def check_connector_declarations(app_configs, **kwargs):  # pylint: disable=unused-argument
    """chat.E101: every `MCP_CONNECTORS` declaration the registry cannot use.

    At runtime the same declaration is only logged and left out; failing here
    catches it at deployment rather than in front of users.
    """
    _definitions, problems = read_declarations()
    return [
        checks.Error(
            problem,
            hint="Fix or remove this connector in MCP_CONNECTORS; see docs/tools.md.",
            obj="MCP_CONNECTORS",
            id="chat.E101",
        )
        for problem in problems
    ]
