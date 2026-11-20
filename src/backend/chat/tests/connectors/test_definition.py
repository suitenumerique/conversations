"""ConnectorDefinition: an immutable, validated description of one connector."""

import dataclasses

import pytest

from chat.connectors import ConnectorDefinition, Tier


def _definition(**overrides) -> ConnectorDefinition:
    fields = {
        "slug": "example",
        "name": "Example",
        "url": "https://mcp.example.org/mcp",
        "tier": Tier.PARTNER,
        "instructions": "Use the Example tools for examples.",
    }
    return ConnectorDefinition(**(fields | overrides))


def test_a_definition_holds_what_it_was_given():
    """Every field reads back as built; timeouts default to no limit."""
    definition = _definition(init_timeout=5.0, read_timeout=30.0)

    assert definition.slug == "example"
    assert definition.name == "Example"
    assert definition.url == "https://mcp.example.org/mcp"
    assert definition.tier is Tier.PARTNER
    assert definition.instructions == "Use the Example tools for examples."
    assert definition.init_timeout == 5.0
    assert definition.read_timeout == 30.0
    assert _definition().init_timeout is None
    assert _definition().read_timeout is None


def test_a_definition_is_immutable():
    """Readers may share a definition: none of them can change it under the others."""
    definition = _definition()

    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.url = "https://elsewhere.example.org/mcp"


def test_a_definition_is_a_value():
    """Two definitions built alike are equal and hash alike."""
    assert _definition() == _definition()
    assert hash(_definition()) == hash(_definition())
    assert _definition() != _definition(url="https://elsewhere.example.org/mcp")


def test_fields_are_keyword_only():
    """Positional construction would silently swap same-typed fields."""
    with pytest.raises(TypeError):
        ConnectorDefinition(  # pylint: disable=too-many-function-args,missing-kwoa
            "example", "Example", "https://mcp.example.org/mcp", Tier.PARTNER, "Use it."
        )


@pytest.mark.parametrize("slug", ["datagouv", "a", "docs_v2", "a" * 20])
def test_valid_slugs(slug):
    """Lowercase letters, digits and underscores, 1 to 20 characters."""
    assert _definition(slug=slug).slug == slug


@pytest.mark.parametrize("slug", ["", "a" * 21, "Datagouv", "data-gouv", "data gouv", "données"])
def test_invalid_slugs_are_refused(slug):
    """The slug prefixes tool names, so anything else is refused at construction."""
    with pytest.raises(ValueError, match="slug"):
        _definition(slug=slug)


@pytest.mark.parametrize("field", ["name", "url"])
def test_empty_required_text_is_refused(field):
    """A connector with no name or no endpoint is not a connector."""
    with pytest.raises(ValueError):
        _definition(**{field: ""})


def test_an_unknown_tier_is_refused():
    """A tier is one of the named ones, never a free string."""
    with pytest.raises(ValueError, match="tier"):
        _definition(tier="trusted")


def test_tiers_compare_as_their_stored_value():
    """Tiers will be stored as text, so each one reads back from its value."""
    assert [tier.value for tier in Tier] == ["internal", "partner", "user"]
    assert Tier("partner") is Tier.PARTNER
