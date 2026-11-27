"""`ConnectorDefinition`: a connector as frozen, validated data."""

import dataclasses

import pytest

from chat.connectors import ConnectorDefinition, Tier
from chat.connectors.definition import DEFAULT_INIT_TIMEOUT, DEFAULT_READ_TIMEOUT


def _declaration(**overrides):
    """A complete, valid declaration, with `overrides` applied.

    An override of None removes the key, so a test can leave a field out.
    """
    declaration = {
        "slug": "sofia",
        "name": "SofIA",
        "url": "https://sofia.example.org/mcp",
        "tier": "partner",
        "instructions": "Use the SofIA tools for questions on the ecological transition.",
    }
    declaration.update(overrides)
    return {key: value for key, value in declaration.items() if value is not None}


def test_a_valid_declaration_builds_a_definition():
    """Every declared field lands on the definition."""
    definition = ConnectorDefinition.from_dict(
        _declaration(init_timeout=2, read_timeout=10, feature_flag="datagouv_connector")
    )

    assert definition.slug == "sofia"
    assert definition.name == "SofIA"
    assert definition.url == "https://sofia.example.org/mcp"
    assert definition.tier is Tier.PARTNER
    assert definition.instructions.startswith("Use the SofIA tools")
    assert definition.init_timeout == 2
    assert definition.read_timeout == 10
    assert definition.feature_flag == "datagouv_connector"


def test_a_definition_is_frozen():
    """Other modules read a definition; none of them may write it."""
    definition = ConnectorDefinition.from_dict(_declaration())

    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.url = "https://elsewhere.example.org/mcp"


def test_a_definition_is_built_with_keywords_only():
    """Positional construction would let two string fields swap silently."""
    with pytest.raises(TypeError):
        ConnectorDefinition(  # pylint: disable=too-many-function-args,missing-kwoa
            "sofia", "SofIA", "https://sofia.example.org/mcp", Tier.PARTNER, "Use it."
        )


@pytest.mark.parametrize("tier", list(Tier))
def test_every_tier_is_accepted(tier):
    """The three tiers are vocabulary: recorded, not enforced yet (ADR 0001 §2)."""
    assert ConnectorDefinition.from_dict(_declaration(tier=tier.value)).tier is tier


def test_the_tiers_are_the_three_of_the_adr():
    """internal, partner, user; nothing else."""
    assert {tier.value for tier in Tier} == {"internal", "partner", "user"}


def test_tier_is_required():
    """A declaration that does not say how far we trust the server is refused.

    Defaulting it would contradict failing closed on configuration.
    """
    with pytest.raises(ValueError, match="tier"):
        ConnectorDefinition.from_dict(_declaration(tier=None))


def test_tier_is_required_in_code_too():
    """Building a definition directly does not get a default either."""
    with pytest.raises(TypeError):
        ConnectorDefinition(  # pylint: disable=missing-kwoa
            slug="sofia",
            name="SofIA",
            url="https://sofia.example.org/mcp",
            instructions="Use it.",
        )


@pytest.mark.parametrize("tier", ["trusted", "PARTNER", "", 1])
def test_an_unknown_tier_is_refused(tier):
    """Only the declared vocabulary, spelt exactly."""
    with pytest.raises(ValueError, match="tier"):
        ConnectorDefinition.from_dict(_declaration(tier=tier))


def test_a_tier_that_is_not_a_tier_is_refused_in_code():
    """A plain string is not a Tier, even when its value matches one."""
    with pytest.raises(ValueError, match="tier"):
        ConnectorDefinition(
            slug="sofia",
            name="SofIA",
            url="https://sofia.example.org/mcp",
            tier="partner",
            instructions="Use it.",
        )


@pytest.mark.parametrize("field", ["read_timout", "transport", "Slug", "auth_token"])
def test_an_unknown_field_is_refused(field):
    """A misspelt field must not fall back silently to a default."""
    with pytest.raises(ValueError, match=field):
        ConnectorDefinition.from_dict(_declaration(**{field: "x"}))


@pytest.mark.parametrize("field", ["slug", "name", "url", "instructions"])
def test_a_missing_field_is_refused(field):
    """Every connector needs an identity, an endpoint and our wording for the model."""
    with pytest.raises(ValueError, match=field):
        ConnectorDefinition.from_dict(_declaration(**{field: None}))


@pytest.mark.parametrize("field", ["name", "url", "instructions"])
def test_an_empty_field_is_refused(field):
    """An empty string is no better than a missing one."""
    with pytest.raises(ValueError, match=field):
        ConnectorDefinition.from_dict(_declaration(**{field: ""}))


@pytest.mark.parametrize("declaration", [None, [], "sofia", 3])
def test_a_declaration_that_is_not_an_object_is_refused(declaration):
    """One object per connector."""
    with pytest.raises(ValueError):
        ConnectorDefinition.from_dict(declaration)


@pytest.mark.parametrize("slug", ["datagouv", "a", "sofia_v2", "abc123", "a" * 20])
def test_a_valid_slug_is_accepted(slug):
    """Lowercase letters, digits and underscores, up to 20 characters."""
    assert ConnectorDefinition.from_dict(_declaration(slug=slug)).slug == slug


@pytest.mark.parametrize(
    "slug", ["", "DataGouv", "data-gouv", "data.gouv", "data gouv", "été", "a" * 21, 7]
)
def test_a_bad_slug_is_refused(slug):
    """The slug becomes a tool-name prefix and a key in history and opt-ins."""
    with pytest.raises(ValueError, match="slug"):
        ConnectorDefinition.from_dict(_declaration(slug=slug))


def test_timeouts_default_to_the_data_gouv_values():
    """The library's five-minute read timeout would let a stalled server cost the turn."""
    definition = ConnectorDefinition.from_dict(_declaration())

    assert definition.init_timeout == DEFAULT_INIT_TIMEOUT == 5.0
    assert definition.read_timeout == DEFAULT_READ_TIMEOUT == 30.0


@pytest.mark.parametrize("field", ["init_timeout", "read_timeout"])
def test_a_zero_timeout_means_no_limit(field):
    """`0` reads as "no limit", as it does elsewhere in Django and httpx."""
    definition = ConnectorDefinition.from_dict(_declaration(**{field: 0}))

    assert getattr(definition, field) is None


@pytest.mark.parametrize("field", ["init_timeout", "read_timeout"])
@pytest.mark.parametrize("value", [-1, -0.5])
def test_a_negative_timeout_is_refused(field, value):
    """A negative deadline expires before the connection starts."""
    with pytest.raises(ValueError, match=field):
        ConnectorDefinition.from_dict(_declaration(**{field: value}))


@pytest.mark.parametrize("field", ["init_timeout", "read_timeout"])
@pytest.mark.parametrize("value", ["5", True, [5], float("nan"), float("inf")])
def test_a_timeout_that_is_not_a_number_is_refused(field, value):
    """`True` is an int to Python, not a number of seconds to us."""
    with pytest.raises(ValueError, match=field):
        ConnectorDefinition.from_dict(_declaration(**{field: value}))


@pytest.mark.parametrize("field", ["init_timeout", "read_timeout"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_a_definition_built_in_code_holds_none_for_no_limit(field, value):
    """In code, no limit is spelt None: `0` there is a mistake, not a convention."""
    with pytest.raises(ValueError, match=field):
        dataclasses.replace(ConnectorDefinition.from_dict(_declaration()), **{field: value})


def test_feature_flag_defaults_to_everyone():
    """No flag: every user the deployment serves is in the cohort."""
    assert ConnectorDefinition.from_dict(_declaration()).feature_flag is None


@pytest.mark.parametrize("flag", ["", 3])
def test_a_feature_flag_that_is_not_a_name_is_refused(flag):
    """An empty flag would read as "everyone", which is weaker than intended."""
    with pytest.raises(ValueError, match="feature_flag"):
        ConnectorDefinition.from_dict(_declaration(feature_flag=flag))


def test_the_model_wordings_are_derived_from_the_name():
    """No connector-specific text is written in code for the forced or unreachable cases."""
    definition = ConnectorDefinition.from_dict(_declaration(name="SofIA"))

    assert definition.forced_instruction == (
        "You must use the SofIA tools before answering the user request."
    )
    assert definition.unreachable_instruction == (
        "SofIA could not be reached for this request. Answer from your own "
        "knowledge or other tools, and tell the user you could not consult SofIA."
    )
    assert definition.unreachable_message == (
        "SofIA could not be reached. Do not call its tools again for this request."
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://exa mple.org/mcp",
        "https://example.org/mcp\n",
        "ftp://example.org/mcp",
        "example.org/mcp",
        "https:///mcp",
        "http://",
    ],
)
def test_a_malformed_url_is_refused(url):
    """Only an http(s) URL with a host: anything else would fail every turn later."""
    with pytest.raises(ValueError, match="url"):
        ConnectorDefinition.from_dict(_declaration(url=url))


@pytest.mark.parametrize(
    "url",
    [
        "https://mcp.data.gouv.fr/mcp",
        "http://host.docker.internal:3100/mcp",
        "http://127.0.0.1:9/mcp",
    ],
)
def test_a_well_formed_url_is_accepted(url):
    """Including plain http and a port, which local servers use."""
    assert ConnectorDefinition.from_dict(_declaration(url=url)).url == url
