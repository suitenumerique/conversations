"""The registry: the only reader of `MCP_CONNECTORS`, read again on every turn."""

import json
import logging

import pytest

from chat.connectors.registry import declared_connectors, read_declarations
from chat.tests.connectors.declarations import datagouv_declaration, sofia_declaration


def _refusals(caplog):
    """(event, connector_id) for each declaration the registry left out."""
    return [
        (record.msg["event"], record.msg.get("connector_id"))
        for record in caplog.records
        if record.name == "chat.mcp_servers"
    ]


def _slugs(definitions):
    return [definition.slug for definition in definitions]


def test_nothing_declared_by_default(settings):
    """A deployment that declares nothing offers nothing and contacts nothing."""
    del settings.MCP_CONNECTORS

    definitions, problems = read_declarations()

    assert definitions == []
    assert problems == []


@pytest.mark.parametrize("value", ["", "[]", []])
def test_an_empty_declaration_is_no_connector(settings, value):
    """Empty in the environment and an empty list mean the same."""
    settings.MCP_CONNECTORS = value

    assert read_declarations() == ([], [])


def test_the_setting_is_read_as_json(settings):
    """The environment holds a JSON list, one object per connector."""
    settings.MCP_CONNECTORS = json.dumps([datagouv_declaration(), sofia_declaration()])

    assert _slugs(declared_connectors()) == ["datagouv", "sofia"]


def test_a_list_is_accepted_as_is(settings):
    """Tests and Python settings may hand the list over already parsed."""
    settings.MCP_CONNECTORS = [sofia_declaration()]

    assert _slugs(declared_connectors()) == ["sofia"]


def test_the_declaration_order_is_kept(settings):
    """The model sees the connectors in the order the deployment wrote them."""
    settings.MCP_CONNECTORS = [sofia_declaration(), datagouv_declaration()]

    assert _slugs(declared_connectors()) == ["sofia", "datagouv"]


def test_the_declarations_are_read_again_on_every_call(settings):
    """Nothing is cached: a removed connector is gone on the next turn."""
    settings.MCP_CONNECTORS = [sofia_declaration()]
    assert _slugs(declared_connectors()) == ["sofia"]

    settings.MCP_CONNECTORS = []
    assert declared_connectors() == []


@pytest.mark.parametrize("value", ["[{", "not json", "{'slug': 'x'}"])
def test_invalid_json_declares_nothing(settings, value):
    """What cannot be parsed cannot be partly trusted."""
    settings.MCP_CONNECTORS = value

    definitions, problems = read_declarations()

    assert definitions == []
    assert len(problems) == 1
    assert "JSON" in problems[0]


@pytest.mark.parametrize("value", ['{"slug": "sofia"}', "3", '"sofia"', {"slug": "sofia"}])
def test_a_declaration_that_is_not_a_list_declares_nothing(settings, value):
    """One list, one object per connector."""
    settings.MCP_CONNECTORS = value

    definitions, problems = read_declarations()

    assert definitions == []
    assert len(problems) == 1
    assert "list" in problems[0]


@pytest.mark.parametrize(
    "bad",
    [
        sofia_declaration(slug="Bad-Slug"),
        sofia_declaration(read_timout=10),
        {k: v for k, v in sofia_declaration().items() if k != "tier"},
        sofia_declaration(tier="trusted"),
        sofia_declaration(init_timeout=-1),
        sofia_declaration(feature_flag="no_such_flag"),
        sofia_declaration(feature_flag="model_dump"),
        sofia_declaration(feature_flag="__class__"),
        sofia_declaration(slug=["sofia"]),
        sofia_declaration(slug={"a": 1}),
        "sofia",
    ],
    ids=[
        "bad slug",
        "unknown field",
        "missing tier",
        "unknown tier",
        "negative timeout",
        "unknown flag",
        "flag that is a model method",
        "flag that is a dunder",
        "unhashable slug",
        "dict slug",
        "not an object",
    ],
)
def test_a_bad_declaration_is_left_out_and_logged(settings, caplog, bad):
    """Fail closed on that connector, open on the others: one typo never costs every turn."""
    settings.MCP_CONNECTORS = [datagouv_declaration(), bad]

    with caplog.at_level(logging.ERROR, logger="chat.mcp_servers"):
        definitions = declared_connectors()

    assert _slugs(definitions) == ["datagouv"]
    assert [event for event, _ in _refusals(caplog)] == ["connector_declaration_refused"]


def test_the_refusal_names_the_connector(settings, caplog):
    """Operators find which declaration to fix."""
    settings.MCP_CONNECTORS = [sofia_declaration(feature_flag="no_such_flag")]

    with caplog.at_level(logging.ERROR, logger="chat.mcp_servers"):
        declared_connectors()

    assert _refusals(caplog) == [("connector_declaration_refused", "sofia")]


def test_a_known_feature_flag_is_accepted(settings):
    """The flag is a `FeatureFlags` field the cohort check can read."""
    settings.MCP_CONNECTORS = [sofia_declaration(feature_flag="datagouv_connector")]

    assert declared_connectors()[0].feature_flag == "datagouv_connector"


def test_duplicate_slugs_are_all_refused(settings):
    """Neither declaration can be told to be the intended one, so neither is offered."""
    settings.MCP_CONNECTORS = [
        sofia_declaration(),
        datagouv_declaration(),
        sofia_declaration(url="https://elsewhere.example.org/mcp"),
    ]

    definitions, problems = read_declarations()

    assert _slugs(definitions) == ["datagouv"]
    assert len(problems) == 1
    assert "sofia" in problems[0]
    assert "duplicate" in problems[0].lower()


def test_a_refused_declaration_is_never_offered_with_a_weaker_setting(settings):
    """A misspelt timeout does not fall back to no limit, nor a bad flag to everyone."""
    settings.MCP_CONNECTORS = [
        sofia_declaration(read_timout=10),
        sofia_declaration(slug="sofia2", feature_flag="no_such_flag"),
    ]

    assert declared_connectors() == []


@pytest.mark.parametrize(
    ("first", "second"),
    [("geo", "geo_ign"), ("a", "a_b"), ("data", "data_gouv_v2")],
)
def test_slugs_whose_tool_prefixes_overlap_are_all_refused(settings, first, second):
    """`geo` + `ign_lookup` and `geo_ign` + `lookup` would both be `geo_ign_lookup`.

    A duplicate tool name ends the agent run, so neither is offered.
    """
    settings.MCP_CONNECTORS = [
        sofia_declaration(slug=first),
        datagouv_declaration(),
        sofia_declaration(slug=second),
    ]

    definitions, problems = read_declarations()

    assert _slugs(definitions) == ["datagouv"]
    assert len(problems) == 1
    assert first in problems[0] and second in problems[0]


def test_slugs_that_only_share_a_start_do_not_collide(settings):
    """`geo` and `geography` give `geo_*` and `geography_*`: no overlap."""
    settings.MCP_CONNECTORS = [sofia_declaration(slug="geo"), sofia_declaration(slug="geography")]

    assert _slugs(declared_connectors()) == ["geo", "geography"]
