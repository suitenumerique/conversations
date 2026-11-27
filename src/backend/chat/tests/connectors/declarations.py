"""Connector declarations the tests share, as a deployment writes them in `MCP_CONNECTORS`."""

# data.gouv's slug: opt-ins, tool names and analytics are keyed on it.
DATAGOUV_SLUG = "datagouv"

# What the model was told about data.gouv before it moved into the declaration,
# verbatim. docs/tools.md gives operators the same text: the move must not
# change a word of what the model reads.
DATAGOUV_INSTRUCTIONS = (
    "The data.gouv.fr tools search France's open-data catalogue: datasets, "
    "the organisations that publish them, and public APIs. Use them when the "
    "answer depends on official French public data (statistics, registries, "
    "local facilities, prices, figures for a commune or département), or "
    "when the user asks for a dataset, a file or an API. Prefer them over "
    "answering such figures from memory. Do not use them for questions about "
    "other countries, general knowledge, administrative procedures, "
    "writing or coding tasks, or "
    "questions about the user's attached documents."
)


def datagouv_declaration(
    url="https://mcp.data.gouv.fr/mcp", init_timeout=5.0, read_timeout=30.0
) -> dict:
    """data.gouv as docs/tools.md tells operators to declare it."""
    return {
        "slug": "datagouv",
        "name": "data.gouv.fr",
        "url": url,
        "tier": "partner",
        "instructions": DATAGOUV_INSTRUCTIONS,
        "init_timeout": init_timeout,
        "read_timeout": read_timeout,
        "feature_flag": "datagouv_connector",
    }


def sofia_declaration(url="https://sofia.example.org/mcp", **overrides) -> dict:
    """A second partner connector, open to everyone."""
    return {
        "slug": "sofia",
        "name": "SofIA",
        "url": url,
        "tier": "partner",
        "instructions": "Use the SofIA tools for questions on the ecological transition.",
        **overrides,
    }
